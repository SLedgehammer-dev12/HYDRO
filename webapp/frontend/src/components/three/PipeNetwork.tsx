import { useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { Html } from "@react-three/drei";
import * as THREE from "three";
import type { SceneSegment } from "../../lib/scene";
import {
  colorForSegment,
  formatDiameter,
  formatPressure,
  formatUtilization,
  formatDistance,
  numberFormat1,
  statusMeta,
  type ColorMode,
  type LayoutSegment,
  type SceneLayout,
} from "./sceneModel";

interface PipeNetworkProps {
  layout: SceneLayout;
  clipPlanes: THREE.Plane[];
  colorMode: ColorMode;
  selectedId: string | null;
  onSelect: (id: string | null) => void;
  showLabels: boolean;
}

interface PipeSegmentProps {
  item: LayoutSegment;
  colorMode: ColorMode;
  layout: SceneLayout;
  clipPlanes: THREE.Plane[];
  selected: boolean;
  showLabels: boolean;
  onSelect: (id: string | null) => void;
}

function SegmentTooltip({ segment }: { segment: SceneSegment }) {
  return (
    <div className="w-[196px] rounded-lg border border-line/80 bg-ink-950/95 px-2.5 py-2 shadow-xl">
      <div className="flex items-center justify-between gap-2">
        <span className="text-[11px] font-semibold text-mist-100">{segment.label}</span>
        <span className="numeric text-[10px] text-mist-500">
          {formatDistance(segment.start_m)}–{formatDistance(segment.end_m)}
        </span>
      </div>
      <dl className="mt-1.5 grid grid-cols-2 gap-x-2 gap-y-1 text-[10px]">
        <dt className="text-mist-500">Basınç</dt>
        <dd className="numeric text-right text-mist-200">{formatPressure(segment.pressure_bar)}</dd>
        <dt className="text-mist-500">Kullanım</dt>
        <dd className="numeric text-right text-mist-200">
          {formatUtilization(segment.utilization)}
        </dd>
        <dt className="text-mist-500">Kot</dt>
        <dd className="numeric text-right text-mist-200">
          {numberFormat1.format(segment.start_elevation_m)} →{" "}
          {numberFormat1.format(segment.end_elevation_m)} m
        </dd>
        <dt className="col-span-2 mt-0.5 text-mist-500">{formatDiameter(segment)}</dt>
      </dl>
    </div>
  );
}

function PipeSegment({
  item,
  colorMode,
  layout,
  clipPlanes,
  selected,
  showLabels,
  onSelect,
}: PipeSegmentProps) {
  const { segment, start, end, mid, quaternion, radius, innerRadius } = item;
  const [hovered, setHovered] = useState(false);
  const length = start.distanceTo(end);
  const color = useMemo(
    () => colorForSegment(segment, colorMode, layout.ranges),
    [segment, colorMode, layout.ranges],
  );
  const innerColor = useMemo(() => color.clone().multiplyScalar(0.5), [color]);
  const meta = statusMeta(segment.status);
  const emissiveIntensity = selected ? 0.5 : hovered ? 0.24 : 0.05;

  useEffect(() => {
    return () => {
      document.body.style.cursor = "";
    };
  }, []);

  if (length < 1e-4) return null;

  const handleOver = (event: { stopPropagation: () => void }) => {
    event.stopPropagation();
    setHovered(true);
    document.body.style.cursor = "pointer";
  };
  const handleOut = () => {
    setHovered(false);
    document.body.style.cursor = "";
  };

  return (
    <group position={mid}>
      <group quaternion={quaternion}>
        <mesh
          castShadow
          receiveShadow
          onPointerOver={handleOver}
          onPointerOut={handleOut}
          onClick={(event) => {
            event.stopPropagation();
            onSelect(selected ? null : segment.id);
          }}
        >
          <cylinderGeometry args={[radius, radius, length, 20, 1, false]} />
          <meshStandardMaterial
            color={color}
            metalness={0.38}
            roughness={0.42}
            emissive={color}
            emissiveIntensity={emissiveIntensity}
            clippingPlanes={clipPlanes}
            clipShadows
          />
        </mesh>

        {/* Interior wall. Invisible inside an intact pipe, revealed by the cutaway. */}
        <mesh>
          <cylinderGeometry args={[innerRadius, innerRadius, length * 0.998, 20, 1, true]} />
          <meshStandardMaterial
            color={innerColor}
            metalness={0.6}
            roughness={0.55}
            side={THREE.BackSide}
            emissive={color}
            emissiveIntensity={0.12}
            clippingPlanes={clipPlanes}
          />
        </mesh>

        {[start, end].map((point, index) => (
          <group key={index} position={[0, (index === 0 ? -1 : 1) * length * 0.5, 0]}>
            <mesh castShadow rotation={[0, 0, 0]}>
              <cylinderGeometry args={[radius * 1.16, radius * 1.16, 0.055, 20, 1, false]} />
              <meshStandardMaterial
                color="#8aa2bb"
                metalness={0.75}
                roughness={0.34}
                clippingPlanes={clipPlanes}
              />
            </mesh>
            <mesh>
              <torusGeometry args={[radius * 1.16, 0.012, 6, 24]} />
              <meshStandardMaterial
                color="#c7d7e6"
                metalness={0.8}
                roughness={0.3}
                clippingPlanes={clipPlanes}
              />
            </mesh>
          </group>
        ))}

        {selected ? (
          <mesh rotation={[-Math.PI / 2, 0, 0]}>
            <torusGeometry args={[radius * 1.34, 0.016, 6, 32]} />
            <meshBasicMaterial color="#22d3ee" toneMapped={false} />
          </mesh>
        ) : null}
      </group>

      {showLabels && !hovered ? (
        <Html
          position={[0, radius + 0.34, 0]}
          center
          zIndexRange={[12, 0]}
          style={{ pointerEvents: "none" }}
          aria-hidden
        >
          <span
            className="numeric whitespace-nowrap rounded border border-line/60 bg-ink-950/75 px-1.5 py-0.5 text-[10px] text-mist-200"
            style={{ borderLeftColor: meta.color, borderLeftWidth: 2 }}
          >
            {segment.label}
          </span>
        </Html>
      ) : null}

      {hovered ? (
        <Html
          position={[0, radius + 0.55, 0]}
          center
          zIndexRange={[24, 12]}
          style={{ pointerEvents: "none" }}
        >
          <SegmentTooltip segment={segment} />
        </Html>
      ) : null}
    </group>
  );
}

function PipeSupports({ layout }: { layout: SceneLayout }) {
  const posts = useRef<THREE.InstancedMesh>(null);
  const saddles = useRef<THREE.InstancedMesh>(null);
  const count = Math.max(1, layout.supports.length);

  useLayoutEffect(() => {
    const dummy = new THREE.Object3D();
    for (let index = 0; index < count; index += 1) {
      const support = layout.supports[index];
      if (!support) continue;
      const height = Math.max(0.04, support.topY - support.baseY);
      dummy.position.set(support.x, support.baseY + height / 2, support.z);
      dummy.rotation.set(0, 0, 0);
      dummy.scale.set(1, height, 1);
      dummy.updateMatrix();
      posts.current?.setMatrixAt(index, dummy.matrix);

      dummy.position.set(support.x, support.topY, support.z);
      dummy.scale.set(1, 1, 1);
      dummy.updateMatrix();
      saddles.current?.setMatrixAt(index, dummy.matrix);
    }
    if (posts.current) {
      posts.current.count = layout.supports.length;
      posts.current.instanceMatrix.needsUpdate = true;
    }
    if (saddles.current) {
      saddles.current.count = layout.supports.length;
      saddles.current.instanceMatrix.needsUpdate = true;
    }
  }, [layout, count]);

  return (
    <group>
      <instancedMesh ref={posts} args={[undefined, undefined, count]} castShadow frustumCulled={false}>
        <cylinderGeometry args={[0.032, 0.045, 1, 6, 1]} />
        <meshStandardMaterial color="#3a4c63" metalness={0.6} roughness={0.55} />
      </instancedMesh>
      <instancedMesh ref={saddles} args={[undefined, undefined, count]} castShadow frustumCulled={false}>
        <boxGeometry args={[0.26, 0.04, 0.17]} />
        <meshStandardMaterial color="#455a73" metalness={0.6} roughness={0.5} />
      </instancedMesh>
    </group>
  );
}

export default function PipeNetwork({
  layout,
  clipPlanes,
  colorMode,
  selectedId,
  onSelect,
  showLabels,
}: PipeNetworkProps) {
  return (
    <group>
      <PipeSupports layout={layout} />
      {layout.segments.map((item) => (
        <PipeSegment
          key={item.segment.id}
          item={item}
          colorMode={colorMode}
          layout={layout}
          clipPlanes={clipPlanes}
          selected={selectedId === item.segment.id}
          showLabels={showLabels}
          onSelect={onSelect}
        />
      ))}
    </group>
  );
}
