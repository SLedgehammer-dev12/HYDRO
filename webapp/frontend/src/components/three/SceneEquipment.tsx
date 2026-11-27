import { useEffect, useState } from "react";
import { SceneHtml } from "./SceneHtml";
import type { ThreeEvent } from "@react-three/fiber";
import * as THREE from "three";
import {
  EQUIPMENT_LABEL,
  formatDistance,
  statusMeta,
  type LayoutEquipment,
  type SceneLayout,
} from "./sceneModel";

interface SceneEquipmentProps {
  layout: SceneLayout;
  selectedId: string | null;
  onSelect: (id: string | null) => void;
  showLabels: boolean;
}

function useEquipmentHover() {
  const [hovered, setHovered] = useState(false);

  useEffect(() => {
    return () => {
      document.body.style.cursor = "";
    };
  }, []);

  const handlers = {
    onPointerOver: (event: ThreeEvent<PointerEvent>) => {
      event.stopPropagation();
      setHovered(true);
      document.body.style.cursor = "pointer";
    },
    onPointerOut: (event: ThreeEvent<PointerEvent>) => {
      event.stopPropagation();
      setHovered(false);
      document.body.style.cursor = "";
    },
  };

  return { hovered, handlers };
}

function Hitbox({
  position,
  size,
  handlers,
  onClick,
}: {
  position: [number, number, number];
  size: [number, number, number];
  handlers: {
    onPointerOver: (event: ThreeEvent<PointerEvent>) => void;
    onPointerOut: (event: ThreeEvent<PointerEvent>) => void;
  };
  onClick: (event: ThreeEvent<MouseEvent>) => void;
}) {
  return (
    <mesh position={position} onClick={onClick} {...handlers}>
      <boxGeometry args={size} />
      <meshBasicMaterial transparent opacity={0} depthWrite={false} colorWrite={false} />
    </mesh>
  );
}

function Gauge({ position, scale = 1 }: { position: [number, number, number]; scale?: number }) {
  return (
    <group position={position} scale={scale}>
      <mesh rotation={[Math.PI / 2, 0, 0]} castShadow>
        <cylinderGeometry args={[0.155, 0.155, 0.05, 20]} />
        <meshStandardMaterial color="#dbe7f2" metalness={0.15} roughness={0.55} />
      </mesh>
      <mesh rotation={[Math.PI / 2, 0, 0]} position={[0, 0, -0.034]} castShadow>
        <cylinderGeometry args={[0.17, 0.17, 0.022, 20]} />
        <meshStandardMaterial color="#7c92aa" metalness={0.72} roughness={0.38} />
      </mesh>
      <mesh position={[0.018, 0.022, 0.032]} rotation={[0, 0, -0.55]}>
        <boxGeometry args={[0.011, 0.115, 0.006]} />
        <meshBasicMaterial color="#0b1220" />
      </mesh>
      <mesh position={[0, 0, 0.034]}>
        <sphereGeometry args={[0.017, 8, 6]} />
        <meshBasicMaterial color="#0b1220" />
      </mesh>
    </group>
  );
}

function StatusLed({ y, color }: { y: number; color: string }) {
  return (
    <mesh position={[0, y, 0]}>
      <sphereGeometry args={[0.045, 10, 8]} />
      <meshBasicMaterial color={color} toneMapped={false} />
    </mesh>
  );
}

function GroundMark({
  y,
  z,
  color,
}: {
  y: number;
  z: number;
  color: string;
}) {
  return (
    <group position={[0, y, z]}>
      <mesh rotation={[-Math.PI / 2, 0, 0]}>
        <ringGeometry args={[0.18, 0.235, 24]} />
        <meshBasicMaterial color={color} transparent opacity={0.55} side={THREE.DoubleSide} />
      </mesh>
    </group>
  );
}

function FlowArrow({
  position,
  color,
  reverse = false,
}: {
  position: [number, number, number];
  color: string;
  reverse?: boolean;
}) {
  return (
    <mesh position={position} rotation={[0, 0, reverse ? Math.PI / 2 : -Math.PI / 2]}>
      <coneGeometry args={[0.055, 0.17, 8]} />
      <meshBasicMaterial color={color} toneMapped={false} />
    </mesh>
  );
}

function ValveModel({
  item,
  align,
  accent,
  emissive,
}: {
  item: LayoutEquipment;
  align: THREE.Quaternion;
  accent: string;
  emissive: number;
}) {
  const r = item.radius;
  const wheelY = r * 2.7;
  return (
    <>
      <mesh quaternion={align} castShadow>
        <cylinderGeometry args={[r * 1.08, r * 1.08, r * 2.4, 18, 1, false]} />
        <meshStandardMaterial
          color="#9db4ca"
          metalness={0.62}
          roughness={0.36}
          emissive={accent}
          emissiveIntensity={emissive}
        />
      </mesh>
      <mesh scale={[1.2, 0.92, 1.2]} castShadow>
        <sphereGeometry args={[r * 1.32, 18, 12]} />
        <meshStandardMaterial
          color="#8299b0"
          metalness={0.62}
          roughness={0.38}
          emissive={accent}
          emissiveIntensity={emissive * 0.6}
        />
      </mesh>
      {[-1, 1].map((direction) => (
        <group key={direction} quaternion={align}>
          <mesh position={[0, direction * r * 1.42, 0]} castShadow>
            <cylinderGeometry args={[r * 1.18, r * 1.18, 0.05, 18]} />
            <meshStandardMaterial color="#b8cbdd" metalness={0.72} roughness={0.32} />
          </mesh>
        </group>
      ))}
      <mesh position={[0, r * 1.75, 0]} castShadow>
        <cylinderGeometry args={[r * 0.16, r * 0.19, r * 1.5, 10]} />
        <meshStandardMaterial color="#93a9bf" metalness={0.7} roughness={0.4} />
      </mesh>
      <mesh position={[0, wheelY, 0]} rotation={[Math.PI / 2, 0, 0]} castShadow>
        <torusGeometry args={[r * 1.28, 0.028, 8, 26]} />
        <meshStandardMaterial color="#e2b15f" metalness={0.5} roughness={0.42} />
      </mesh>
      {[0, 1, 2, 3].map((spoke) => (
        <mesh
          key={spoke}
          position={[0, wheelY, 0]}
          rotation={[0, (spoke * Math.PI) / 4, Math.PI / 2]}
        >
          <cylinderGeometry args={[0.012, 0.012, r * 2.4, 5]} />
          <meshStandardMaterial color="#d3a758" metalness={0.5} roughness={0.45} />
        </mesh>
      ))}
      <StatusLed y={wheelY + 0.1} color={accent} />
    </>
  );
}

function PumpModel({
  item,
  accent,
  emissive,
}: {
  item: LayoutEquipment;
  accent: string;
  emissive: number;
}) {
  const z = item.side * 1.15;
  const pipeHeight = item.pipePoint.y - item.groundPoint.y;
  return (
    <group position={[0, item.groundPoint.y - item.pipePoint.y, z]}>
      <mesh position={[0, 0.05, 0]} castShadow receiveShadow>
        <boxGeometry args={[1.15, 0.1, 0.72]} />
        <meshStandardMaterial color="#26374d" metalness={0.5} roughness={0.6} />
      </mesh>
      <mesh position={[-0.16, 0.3, 0]} rotation={[0, 0, Math.PI / 2]} castShadow>
        <cylinderGeometry args={[0.16, 0.16, 0.58, 16]} />
        <meshStandardMaterial
          color="#6c8aa6"
          metalness={0.6}
          roughness={0.4}
          emissive={accent}
          emissiveIntensity={emissive * 0.5}
        />
      </mesh>
      <mesh position={[0.28, 0.3, 0]} rotation={[Math.PI / 2, 0, 0]} castShadow>
        <cylinderGeometry args={[0.23, 0.23, 0.24, 18]} />
        <meshStandardMaterial
          color="#9db4ca"
          metalness={0.62}
          roughness={0.36}
          emissive={accent}
          emissiveIntensity={emissive}
        />
      </mesh>
      <mesh position={[0.06, 0.3, 0]} castShadow>
        <cylinderGeometry args={[0.055, 0.055, 0.16, 10]} />
        <meshStandardMaterial color="#c3d4e4" metalness={0.7} roughness={0.3} />
      </mesh>
      <mesh position={[-0.16, 0.52, 0]} castShadow>
        <boxGeometry args={[0.34, 0.1, 0.22]} />
        <meshStandardMaterial color="#31465e" metalness={0.5} roughness={0.55} />
      </mesh>
      <mesh position={[0.06, pipeHeight, z * -0.55]} rotation={[Math.PI / 2, 0, 0]} castShadow>
        <cylinderGeometry args={[0.075, 0.075, Math.abs(z) * 1.1, 12]} />
        <meshStandardMaterial color="#7f96ad" metalness={0.62} roughness={0.4} />
      </mesh>
      <FlowArrow position={[0, 0.72, 0]} color={accent} />
      <StatusLed y={0.62} color={accent} />
    </group>
  );
}

function TestHeadModel({
  item,
  accent,
  emissive,
}: {
  item: LayoutEquipment;
  accent: string;
  emissive: number;
}) {
  const r = item.radius;
  const riser = 1.15;
  return (
    <>
      <mesh position={[0, 0.04, 0]} castShadow>
        <cylinderGeometry args={[r * 1.32, r * 1.42, 0.08, 16]} />
        <meshStandardMaterial color="#9db4ca" metalness={0.7} roughness={0.34} />
      </mesh>
      <mesh position={[0, riser / 2, 0]} castShadow>
        <cylinderGeometry args={[Math.max(0.05, r * 0.42), Math.max(0.055, r * 0.46), riser, 12]} />
        <meshStandardMaterial
          color="#8ba3ba"
          metalness={0.66}
          roughness={0.38}
          emissive={accent}
          emissiveIntensity={emissive * 0.6}
        />
      </mesh>
      <mesh position={[0, riser, 0]} castShadow>
        <cylinderGeometry args={[r * 0.78, r * 0.72, 0.055, 14]} />
        <meshStandardMaterial color="#b8cbdd" metalness={0.72} roughness={0.3} />
      </mesh>
      <mesh position={[0, riser + 0.28, 0]} castShadow>
        <cylinderGeometry args={[0.045, 0.05, 0.5, 10]} />
        <meshStandardMaterial color="#93a9bf" metalness={0.68} roughness={0.4} />
      </mesh>
      <Gauge position={[0, riser + 0.62, 0.015]} scale={1.15} />
      <mesh position={[r * 0.66, riser * 0.55, 0]} rotation={[0, 0, Math.PI / 2]} castShadow>
        <cylinderGeometry args={[0.028, 0.028, r * 1.5, 8]} />
        <meshStandardMaterial color="#c3d4e4" metalness={0.7} roughness={0.35} />
      </mesh>
      <mesh position={[r * 1.18, riser * 0.55, 0]} rotation={[0, Math.PI / 2, 0]}>
        <torusGeometry args={[0.16, 0.022, 6, 18]} />
        <meshStandardMaterial color="#e2b15f" metalness={0.5} roughness={0.42} />
      </mesh>
      <StatusLed y={riser + 0.98} color={accent} />
    </>
  );
}

function LauncherModel({
  item,
  accent,
  emissive,
}: {
  item: LayoutEquipment;
  accent: string;
  emissive: number;
}) {
  const z = item.side * 1.15;
  const barrelR = Math.max(0.16, item.radius * 1.38);
  const neckR = Math.max(0.11, item.radius * 0.96);
  const barrelY = 0.66;
  const fromPipe = item.pipePoint.y - item.groundPoint.y;
  const isLauncher = item.equipment.type === "pig-launcher";
  const dir = isLauncher ? 1 : -1;

  return (
    <group position={[0, item.groundPoint.y - item.pipePoint.y, z]}>
      {/* Ağır beton/çelik kızak kaidesi */}
      <mesh position={[0, 0.04, 0]} castShadow receiveShadow>
        <boxGeometry args={[1.65, 0.08, 0.68]} />
        <meshStandardMaterial color="#1f2e42" metalness={0.45} roughness={0.65} />
      </mesh>
      {/* Çift eyer (saddle) desteği */}
      {[-0.36, 0.32].map((x) => (
        <mesh key={x} position={[x, 0.28, 0]} castShadow receiveShadow>
          <boxGeometry args={[0.12, 0.42, 0.24]} />
          <meshStandardMaterial color="#31465e" metalness={0.55} roughness={0.5} />
        </mesh>
      ))}
      {/* Ana büyük çaplı varil (pig barrel) */}
      <mesh
        position={[dir * -0.16, barrelY, 0]}
        rotation={[0, 0, Math.PI / 2]}
        castShadow
      >
        <cylinderGeometry args={[barrelR, barrelR, 0.9, 22]} />
        <meshStandardMaterial
          color="#7f96ad"
          metalness={0.64}
          roughness={0.36}
          emissive={accent}
          emissiveIntensity={emissive * 0.55}
        />
      </mesh>
      {/* Eksantrik redüksiyon konisi (varilden ana hat çapına geçiş) */}
      <mesh
        position={[dir * 0.42, barrelY - 0.015, 0]}
        rotation={[0, 0, dir * (-Math.PI / 2)]}
        castShadow
      >
        <cylinderGeometry args={[neckR, barrelR, 0.3, 22]} />
        <meshStandardMaterial
          color="#92a9c0"
          metalness={0.68}
          roughness={0.34}
          emissive={accent}
          emissiveIntensity={emissive * 0.4}
        />
      </mesh>
      {/* Hızlı açılır kapak (quick-opening closure) + kilitleme kelepçesi */}
      <mesh
        position={[dir * -0.63, barrelY, 0]}
        rotation={[0, 0, Math.PI / 2]}
        castShadow
      >
        <cylinderGeometry args={[barrelR * 1.14, barrelR * 1.14, 0.06, 22]} />
        <meshStandardMaterial color="#cbd9e8" metalness={0.78} roughness={0.28} />
      </mesh>
      <mesh
        position={[dir * -0.67, barrelY, 0]}
        rotation={[0, 0, Math.PI / 2]}
        castShadow
      >
        <cylinderGeometry args={[barrelR * 0.92, barrelR * 1.05, 0.05, 20]} />
        <meshStandardMaterial color="#e2b15f" metalness={0.55} roughness={0.4} />
      </mesh>
      {/* Kicker / bypass hattı + izolasyon vanası el çarkı */}
      <mesh position={[0, barrelY + barrelR * 0.85, 0]} rotation={[0, 0, Math.PI / 2]} castShadow>
        <cylinderGeometry args={[0.036, 0.036, 0.62, 10]} />
        <meshStandardMaterial color="#a6bcd1" metalness={0.7} roughness={0.35} />
      </mesh>
      <mesh position={[dir * -0.26, barrelY + barrelR * 0.45, 0]} castShadow>
        <cylinderGeometry args={[0.032, 0.032, barrelR * 0.82, 10]} />
        <meshStandardMaterial color="#a6bcd1" metalness={0.7} roughness={0.35} />
      </mesh>
      <mesh position={[dir * 0.05, barrelY + barrelR * 1.18, 0]} rotation={[Math.PI / 2, 0, 0]}>
        <torusGeometry args={[barrelR * 0.44, 0.022, 8, 22]} />
        <meshStandardMaterial color="#e2b15f" metalness={0.5} roughness={0.42} />
      </mesh>
      {/* Tahliye / vent kolonu ve manometre */}
      <mesh position={[dir * -0.42, barrelY + barrelR * 1.28, 0]} castShadow>
        <cylinderGeometry args={[0.024, 0.028, 0.28, 8]} />
        <meshStandardMaterial color="#b8cbdd" metalness={0.72} roughness={0.32} />
      </mesh>
      <Gauge position={[dir * -0.42, barrelY + barrelR * 1.28 + 0.22, 0.02]} scale={0.95} />
      {/* Ana boru bağlantı kolu */}
      <mesh position={[dir * 0.56, fromPipe, z * -0.5]} rotation={[Math.PI / 2, 0, 0]} castShadow>
        <cylinderGeometry args={[neckR * 0.72, neckR * 0.72, Math.abs(z) * 1.05, 14]} />
        <meshStandardMaterial color="#7f96ad" metalness={0.62} roughness={0.4} />
      </mesh>
      <FlowArrow position={[dir * 0.15, barrelY + barrelR * 1.68, 0]} color={accent} reverse={!isLauncher} />
      <StatusLed y={barrelY + barrelR * 1.55} color={accent} />
    </group>
  );
}

function GaugeStandModel({
  item,
  accent,
  emissive,
}: {
  item: LayoutEquipment;
  accent: string;
  emissive: number;
}) {
  return (
    <>
      <mesh position={[0, 0.33, 0]} castShadow>
        <cylinderGeometry args={[0.045, 0.065, 0.66, 10]} />
        <meshStandardMaterial
          color="#8ba3ba"
          metalness={0.66}
          roughness={0.38}
          emissive={accent}
          emissiveIntensity={emissive * 0.6}
        />
      </mesh>
      <mesh position={[0, 0.62, 0]} castShadow>
        <cylinderGeometry args={[item.radius * 0.9, item.radius * 0.9, 0.05, 12]} />
        <meshStandardMaterial color="#b8cbdd" metalness={0.72} roughness={0.3} />
      </mesh>
      <Gauge position={[0, 0.8, 0.02]} scale={1.25} />
      <StatusLed y={1.1} color={accent} />
    </>
  );
}

function EquipmentLabel({
  label,
  type,
  status,
  distance,
  hovered,
}: {
  label: string;
  type: LayoutEquipment["equipment"]["type"];
  status: LayoutEquipment["equipment"]["status"];
  distance: number;
  hovered: boolean;
}) {
  const meta = statusMeta(status);
  if (hovered) {
    return (
      <div className="w-[190px] rounded-lg border border-line/80 bg-ink-950/95 px-2.5 py-2 shadow-xl">
        <p className="text-[11px] font-semibold text-mist-100">{label}</p>
        <p className="mt-0.5 text-[10px] text-mist-500">
          {EQUIPMENT_LABEL[type]} · {formatDistance(distance)}
        </p>
        <p className="mt-1 flex items-center gap-1.5 text-[10px] text-mist-200">
          <span className={`inline-block h-1.5 w-1.5 rounded-full ${meta.dot}`} />
          {meta.label}
        </p>
      </div>
    );
  }
  return (
    <span className="numeric whitespace-nowrap rounded border border-line/60 bg-ink-950/75 px-1.5 py-0.5 text-[10px] text-mist-200">
      <span
        className="mr-1 inline-block h-1.5 w-1.5 rounded-full align-middle"
        style={{ backgroundColor: meta.color }}
      />
      {label}
    </span>
  );
}

function EquipmentItem({
  layout,
  item,
  selected,
  showLabels,
  onSelect,
}: {
  layout: SceneLayout;
  item: LayoutEquipment;
  selected: boolean;
  showLabels: boolean;
  onSelect: (id: string | null) => void;
}) {
  const { hovered, handlers } = useEquipmentHover();
  const equipment = item.equipment;
  const meta = statusMeta(equipment.status);
  const segment = layout.segmentAt(equipment.distance_m);
  const align = segment.quaternion;
  const accent = meta.color;
  const emissive = selected ? 0.5 : hovered ? 0.28 : 0.05;
  const r = item.radius;
  const groundOffset = item.groundPoint.y - item.pipePoint.y;
  const distance = Math.max(0, equipment.distance_m);

  let labelY = r * 3.3;
  let hitbox: { position: [number, number, number]; size: [number, number, number] } = {
    position: [0, r * 1.5, 0],
    size: [r * 3.6, r * 4.4, r * 3.6],
  };
  let groundZ = 0;

  switch (equipment.type) {
    case "pump":
      labelY = groundOffset + 1.75;
      groundZ = item.side * 1.15;
      hitbox = {
        position: [0, groundOffset + 0.45, groundZ],
        size: [1.5, 1.3, 1.3],
      };
      break;
    case "test-head":
      labelY = 2.25;
      hitbox = { position: [0, 1.0, 0], size: [0.9, 2.2, 0.9] };
      break;
    case "pig-launcher":
    case "pig-receiver":
      labelY = groundOffset + 2.05;
      groundZ = item.side * 1.25;
      hitbox = {
        position: [0, groundOffset + 0.65, groundZ],
        size: [1.7, 1.5, 1.4],
      };
      break;
    case "gauge":
      labelY = 1.3;
      hitbox = { position: [0, 0.75, 0], size: [0.75, 1.5, 0.75] };
      break;
    default:
      break;
  }

  return (
    <group position={item.pipePoint}>
      {equipment.type === "valve" ? (
        <ValveModel item={item} align={align} accent={accent} emissive={emissive} />
      ) : null}
      {equipment.type === "pump" ? (
        <PumpModel item={item} accent={accent} emissive={emissive} />
      ) : null}
      {equipment.type === "test-head" ? (
        <TestHeadModel item={item} accent={accent} emissive={emissive} />
      ) : null}
      {equipment.type === "pig-launcher" || equipment.type === "pig-receiver" ? (
        <LauncherModel item={item} accent={accent} emissive={emissive} />
      ) : null}
      {equipment.type === "gauge" ? (
        <GaugeStandModel item={item} accent={accent} emissive={emissive} />
      ) : null}

      <GroundMark y={groundOffset + 0.02} z={groundZ} color={accent} />

      <Hitbox
        position={hitbox.position}
        size={hitbox.size}
        handlers={handlers}
        onClick={(event) => {
          event.stopPropagation();
          onSelect(selected ? null : equipment.id);
        }}
      />

      {showLabels || hovered ? (
        <SceneHtml
          position={[0, labelY, 0]}
          center
          zIndexRange={hovered ? [24, 14] : [14, 2]}
        >
          <EquipmentLabel
            label={equipment.label}
            type={equipment.type}
            status={equipment.status}
            distance={distance}
            hovered={hovered}
          />
        </SceneHtml>
      ) : null}
    </group>
  );
}

export default function SceneEquipment({
  layout,
  selectedId,
  onSelect,
  showLabels,
}: SceneEquipmentProps) {
  return (
    <group>
      {layout.equipment.map((item) => (
        <EquipmentItem
          key={item.equipment.id}
          layout={layout}
          item={item}
          selected={selectedId === item.equipment.id}
          showLabels={showLabels}
          onSelect={onSelect}
        />
      ))}
    </group>
  );
}
