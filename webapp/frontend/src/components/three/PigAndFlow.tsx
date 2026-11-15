import { useEffect, useMemo, useRef } from "react";
import { Html } from "@react-three/drei";
import { useFrame } from "@react-three/fiber";
import * as THREE from "three";
import {
  clamp,
  numberFormat1,
  type SceneLayout,
} from "./sceneModel";

const UP = new THREE.Vector3(0, 1, 0);

export interface PigHandle {
  current: THREE.Vector3;
}

interface PigProps {
  layout: SceneLayout;
  startDistance: number;
  speedMps: number | null;
  playing: boolean;
  rate: number;
  visible: boolean;
  showLabels: boolean;
  reducedMotion: boolean;
  positionRef: PigHandle;
}

/** Glowing inspection pig inside the pipe; the beacon marks its station when the pipe is closed. */
export default function PipelinePig({
  layout,
  startDistance,
  speedMps,
  playing,
  rate,
  visible,
  showLabels,
  reducedMotion,
  positionRef,
}: PigProps) {
  const pigRef = useRef<THREE.Group>(null);
  const beaconRef = useRef<THREE.Group>(null);
  const stationRingRef = useRef<THREE.Mesh>(null);
  const haloRef = useRef<THREE.Mesh>(null);
  const distanceRef = useRef(startDistance);
  const temp = useMemo(() => new THREE.Vector3(), []);
  const visualSpeed = (layout.totalLengthM / 22) * Math.max(1, rate);

  useEffect(() => {
    distanceRef.current = startDistance;
  }, [startDistance]);

  useFrame((state, delta) => {
    const pig = pigRef.current;
    if (!pig || !visible) return;

    if (playing && !reducedMotion) {
      const step = visualSpeed * Math.min(delta, 0.05);
      distanceRef.current = (distanceRef.current + step) % layout.totalLengthM;
    }

    layout.sample(distanceRef.current, temp);
    pig.position.copy(temp);
    const segment = layout.segmentAt(distanceRef.current);
    // The capsule's long axis is local Y, matching the cylinder convention.
    pig.quaternion.copy(segment.quaternion);
    positionRef.current.copy(temp);

    if (stationRingRef.current) {
      stationRingRef.current.position.copy(temp);
      stationRingRef.current.quaternion.copy(segment.ringQuaternion);
      const ringScale = segment.radius * 1.55;
      stationRingRef.current.scale.setScalar(ringScale);
    }

    if (beaconRef.current) {
      beaconRef.current.position.set(temp.x, temp.y + 1.05, 0);
    }
    if (haloRef.current) {
      const pulse = reducedMotion ? 1 : 1 + Math.sin(state.clock.elapsedTime * 2.6) * 0.14;
      haloRef.current.scale.setScalar(pulse);
    }
  });

  if (!visible) return null;

  const rateLabel = speedMps
    ? `${numberFormat1.format(speedMps)} m/s · ${rate}×`
    : `${rate}×`;

  return (
    <group>
      <group ref={pigRef}>
        <mesh castShadow>
          <capsuleGeometry args={[0.145, 0.52, 4, 14]} />
          <meshStandardMaterial
            color="#f8c56b"
            emissive="#f59e0b"
            emissiveIntensity={0.55}
            metalness={0.45}
            roughness={0.35}
          />
        </mesh>
        {[-0.2, 0, 0.2].map((offset) => (
          <mesh key={offset} position={[0, offset, 0]} rotation={[Math.PI / 2, 0, 0]}>
            <torusGeometry args={[0.152, 0.018, 6, 18]} />
            <meshStandardMaterial
              color="#1e2a3a"
              metalness={0.4}
              roughness={0.6}
              emissive="#22d3ee"
              emissiveIntensity={0.2}
            />
          </mesh>
        ))}
        <mesh ref={haloRef}>
          <sphereGeometry args={[0.27, 14, 10]} />
          <meshBasicMaterial
            color="#67e8f9"
            transparent
            opacity={0.12}
            blending={THREE.AdditiveBlending}
            depthWrite={false}
            toneMapped={false}
          />
        </mesh>
        <pointLight color="#fcd34d" intensity={1.1} distance={1.6} decay={2} />
      </group>

      <mesh ref={stationRingRef} renderOrder={3}>
        <torusGeometry args={[1, 0.045, 6, 32]} />
        <meshBasicMaterial
          color="#fbbf24"
          transparent
          opacity={0.72}
          blending={THREE.AdditiveBlending}
          depthWrite={false}
          toneMapped={false}
        />
      </mesh>

      <group ref={beaconRef}>
        <mesh position={[0, 0.16, 0]}>
          <coneGeometry args={[0.07, 0.22, 8]} />
          <meshBasicMaterial color="#fbbf24" toneMapped={false} />
        </mesh>
        <mesh position={[0, 0.42, 0]}>
          <cylinderGeometry args={[0.005, 0.005, 0.5, 4]} />
          <meshBasicMaterial color="#fbbf24" toneMapped={false} />
        </mesh>        {showLabels ? (
          <Html
            position={[0, 0.62, 0]}
            center
            zIndexRange={[16, 2]}
            style={{ pointerEvents: "none" }}
            aria-hidden
          >
            <span className="numeric whitespace-nowrap rounded border border-amber-400/50 bg-ink-950/80 px-1.5 py-0.5 text-[10px] text-amber-300">
              PIG · {rateLabel}
            </span>
          </Html>
        ) : null}
      </group>
    </group>
  );
}

interface FlowProps {
  layout: SceneLayout;
  speedMps: number | undefined;
  enabled: boolean;
  reducedMotion: boolean;
  compact: boolean;
}

/** Instanced tracers along the pipe; the visual speed is derived from flow_speed_m_per_s. */
export function FlowParticles({
  layout,
  speedMps,
  enabled,
  reducedMotion,
  compact,
}: FlowProps) {
  const meshRef = useRef<THREE.InstancedMesh>(null);
  const count = compact ? 64 : 140;
  const seeded = useMemo(
    () =>
      Array.from({ length: count }, (_, index) => ({
        offset: (index * 0.6180339887498949) % 1,
        phase: (index * 2.399963229728653) % (Math.PI * 2),
        drift: 0.72 + ((index * 37) % 100) / 130,
      })),
    [count],
  );
  const tempPosition = useMemo(() => new THREE.Vector3(), []);
  const tempSide = useMemo(() => new THREE.Vector3(), []);
  const tempUp = useMemo(() => new THREE.Vector3(), []);
  const dummy = useMemo(() => new THREE.Object3D(), []);
  const linearSpeed = clamp(
    typeof speedMps === "number" && Number.isFinite(speedMps) ? speedMps : 0.8,
    0.25,
    3,
  );

  useEffect(() => {
    const mesh = meshRef.current;
    if (!mesh) return;
    mesh.instanceMatrix.setUsage(THREE.DynamicDrawUsage);
  }, []);

  useFrame((state) => {
    const mesh = meshRef.current;
    if (!mesh) return;
    const time = reducedMotion ? 0 : state.clock.elapsedTime;
    const fractionSpeed = 0.018 + linearSpeed * 0.032;

    for (let index = 0; index < count; index += 1) {
      const particle = seeded[index];
      const fraction = (particle.offset + time * fractionSpeed * particle.drift) % 1;
      const distance = fraction * layout.totalLengthM;
      layout.sample(distance, tempPosition);
      const segment = layout.segmentAt(distance);
      const radius = segment.radius * 1.18;

      tempSide.crossVectors(segment.direction, UP);
      if (tempSide.lengthSq() < 1e-6) tempSide.set(0, 0, 1);
      tempSide.normalize();
      tempUp.crossVectors(tempSide, segment.direction).normalize();

      const angle = particle.phase + time * 0.4;
      tempPosition.addScaledVector(tempSide, Math.cos(angle) * radius);
      tempPosition.addScaledVector(tempUp, Math.sin(angle) * radius);

      dummy.position.copy(tempPosition);
      dummy.rotation.set(0, 0, 0);
      dummy.scale.setScalar(index % 4 === 0 ? 0.03 : 0.021);
      dummy.updateMatrix();
      mesh.setMatrixAt(index, dummy.matrix);
    }
    mesh.instanceMatrix.needsUpdate = true;
  });

  if (!enabled) return null;

  return (
    <instancedMesh
      ref={meshRef}
      args={[undefined, undefined, count]}
      frustumCulled={false}
      renderOrder={2}
    >
      <sphereGeometry args={[1, 6, 4]} />
      <meshBasicMaterial
        color="#67e8f9"
        transparent
        opacity={0.9}
        blending={THREE.AdditiveBlending}
        depthWrite={false}
        toneMapped={false}
      />
    </instancedMesh>
  );
}
