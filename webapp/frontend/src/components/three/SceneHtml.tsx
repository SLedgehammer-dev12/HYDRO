import {
  createContext,
  useContext,
  useId,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
  type CSSProperties,
  type ReactNode,
} from "react";
import { useFrame, useThree } from "@react-three/fiber";
import * as THREE from "three";

/**
 * Sahne içi HTML etiketleri.
 *
 * Neden drei'nin `Html` bileşeni değil: drei her etiket için ayrı bir React
 * kökü (`createRoot`) açıyor ve bu kökü R3F commit'i sırasında senkron olarak
 * söküyor. React 19 üretim derlemesinde bu iç içe kök sökümü
 * "Failed to execute 'removeChild' on 'Node'" hatası üretiyor (etiket
 * kapatıldığında veya 3D sayfadan çıkıldığında).
 *
 * Çözüm: etiket DOM'u ana React ağacında, sahnenin üstünde bir katmanda
 * render edilir. Canvas içindeki `SceneHtml` yalnızca her karede ekran
 * koordinatını hesaplayıp ilgili DOM düğümünü konumlandırır. Böylece ek DOM
 * düğümü React'in normal yaşam döngüsüyle kaldırılır.
 */

interface SceneLabelEntry {
  id: string;
  node: ReactNode;
  center: boolean;
  style?: CSSProperties;
  className?: string;
}

interface SceneLabelApi {
  register: (entry: SceneLabelEntry) => void;
  unregister: (id: string) => void;
  setNode: (id: string, element: HTMLDivElement | null) => void;
  getNode: (id: string) => HTMLDivElement | null;
}

const SceneLabelContext = createContext<SceneLabelApi | null>(null);

/** Sahne etiket katmanı + sağlayıcı. Canvas'ı ve DOM katmanını birlikte sarar. */
export function SceneLabels({ children }: { children: ReactNode }) {
  const [entries, setEntries] = useState<SceneLabelEntry[]>([]);
  const nodes = useRef(new Map<string, HTMLDivElement>());

  const api = useMemo<SceneLabelApi>(
    () => ({
      register: (entry) =>
        setEntries((current) => {
          const index = current.findIndex((item) => item.id === entry.id);
          if (index === -1) return [...current, entry];
          const next = current.slice();
          next[index] = entry;
          return next;
        }),
      unregister: (id) => {
        nodes.current.delete(id);
        setEntries((current) => current.filter((item) => item.id !== id));
      },
      setNode: (id, element) => {
        if (element) nodes.current.set(id, element);
        else nodes.current.delete(id);
      },
      getNode: (id) => nodes.current.get(id) ?? null,
    }),
    [],
  );

  return (
    <SceneLabelContext.Provider value={api}>
      {children}
      <div className="pointer-events-none absolute inset-0 overflow-hidden" aria-hidden>
        {entries.map((entry) => (
          <div
            key={entry.id}
            ref={(element) => api.setNode(entry.id, element)}
            className="absolute left-0 top-0"
            style={{ display: "none" }}
          >
            <div
              className={entry.className}
              style={{
                position: "absolute",
                transform: entry.center ? "translate3d(-50%,-50%,0)" : "none",
                ...entry.style,
              }}
            >
              {entry.node}
            </div>
          </div>
        ))}
      </div>
    </SceneLabelContext.Provider>
  );
}

export interface SceneHtmlProps {
  position: [number, number, number];
  children: ReactNode;
  center?: boolean;
  zIndexRange?: [number, number];
  style?: CSSProperties;
  className?: string;
  /** Etiket görünür değilken DOM'da kalır ama gizlenir. */
  visible?: boolean;
}

const projectVector = new THREE.Vector3();
const cameraVector = new THREE.Vector3();
const directionVector = new THREE.Vector3();
const viewDirection = new THREE.Vector3();

function calculatePosition(
  element: THREE.Object3D,
  camera: THREE.Camera,
  size: { width: number; height: number },
): [number, number] {
  const objectPosition = projectVector.setFromMatrixPosition(element.matrixWorld);
  objectPosition.project(camera);
  const halfWidth = size.width / 2;
  const halfHeight = size.height / 2;
  return [objectPosition.x * halfWidth + halfWidth, -(objectPosition.y * halfHeight) + halfHeight];
}

function objectZIndex(
  element: THREE.Object3D,
  camera: THREE.Camera,
  zIndexRange: [number, number],
): number {
  if (camera instanceof THREE.PerspectiveCamera || camera instanceof THREE.OrthographicCamera) {
    const objectPosition = projectVector.setFromMatrixPosition(element.matrixWorld);
    const cameraPosition = cameraVector.setFromMatrixPosition(camera.matrixWorld);
    const distance = objectPosition.distanceTo(cameraPosition);
    const depthFactor = (zIndexRange[1] - zIndexRange[0]) / (camera.far - camera.near);
    const range = zIndexRange[1] - depthFactor * camera.far;
    return Math.round(depthFactor * distance + range);
  }
  return zIndexRange[0];
}

function isBehindCamera(element: THREE.Object3D, camera: THREE.Camera): boolean {
  camera.getWorldDirection(viewDirection);
  const objectPosition = projectVector.setFromMatrixPosition(element.matrixWorld);
  const cameraPosition = cameraVector.setFromMatrixPosition(camera.matrixWorld);
  const direction = directionVector.subVectors(objectPosition, cameraPosition);
  return direction.angleTo(viewDirection) > Math.PI / 2;
}

/** Canvas içinde konum çapası; DOM içeriğini etiket katmanına taşır. */
export function SceneHtml({
  position,
  children,
  center = false,
  zIndexRange = [12, 0],
  style,
  className,
  visible = true,
}: SceneHtmlProps) {
  const { camera, size } = useThree();
  const api = useContext(SceneLabelContext);
  const id = useId();
  const groupRef = useRef<THREE.Group>(null);
  const lastPosition = useRef<[number, number]>([Number.NaN, Number.NaN]);

  useLayoutEffect(() => {
    if (!api) return;
    api.register({ id, node: children, center, style, className });
    return () => api.unregister(id);
  }, [api, id, children, center, style, className]);

  useFrame(() => {
    const group = groupRef.current;
    if (!group || !api) return;
    const element = api.getNode(id);
    if (!element) return;

    camera.updateMatrixWorld();
    group.updateWorldMatrix(true, false);

    if (!visible || isBehindCamera(group, camera)) {
      element.style.display = "none";
      return;
    }
    element.style.display = "block";

    const [x, y] = calculatePosition(group, camera, size);
    if (
      Number.isNaN(lastPosition.current[0]) ||
      Math.abs(lastPosition.current[0] - x) > 0.01 ||
      Math.abs(lastPosition.current[1] - y) > 0.01
    ) {
      element.style.transform = `translate3d(${x}px, ${y}px, 0)`;
      lastPosition.current = [x, y];
    }
    element.style.zIndex = String(objectZIndex(group, camera, zIndexRange));
  });

  return <group ref={groupRef} position={position} />;
}
