import { useEffect, useMemo } from "react";
import { ContactShadows, Grid, Line } from "@react-three/drei";
import * as THREE from "three";
import { SceneHtml } from "./SceneHtml";
import type { SceneLayout } from "./sceneModel";

interface SceneEnvironmentProps {
  layout: SceneLayout;
  showLabels: boolean;
  showLandmarks: boolean;
  highQuality: boolean;
  reducedMotion: boolean;
}

function SceneLights({ layout, highQuality }: { layout: SceneLayout; highQuality: boolean }) {
  const span = layout.span;

  return (
    <>
      <hemisphereLight args={["#b7ecff", "#08111f", 0.75]} />
      <ambientLight intensity={0.35} />
      <directionalLight
        position={[span * 0.35, span * 0.85, span * 0.55]}
        intensity={2.1}
        color="#eaf7ff"
        castShadow={highQuality}
        shadow-mapSize-width={1024}
        shadow-mapSize-height={1024}
        shadow-bias={-0.0005}
        shadow-camera-near={1}
        shadow-camera-far={span * 3}
        shadow-camera-left={-span * 0.75}
        shadow-camera-right={span * 0.75}
        shadow-camera-top={span * 0.75}
        shadow-camera-bottom={-span * 0.75}
      />
      <directionalLight
        position={[-span * 0.5, span * 0.25, -span * 0.4]}
        intensity={0.5}
        color="#3f9bd6"
      />
      <pointLight
        position={[layout.center.x, layout.center.y + 1.2, 2]}
        intensity={0.35}
        distance={span * 0.9}
        color="#22d3ee"
      />
    </>
  );
}

function Terrain({ layout }: { layout: SceneLayout }) {
  const { geometry, ridgeLine, edgeLineLeft, edgeLineRight } = layout.terrain;

  useEffect(() => {
    return () => {
      geometry.dispose();
    };
  }, [geometry]);

  return (
    <group>
      <mesh receiveShadow position={[0, 0, 0]}>
        <primitive object={geometry} attach="geometry" />
        <meshStandardMaterial
          vertexColors
          roughness={0.96}
          metalness={0.02}
          polygonOffset
          polygonOffsetFactor={1}
          polygonOffsetUnits={1}
        />
      </mesh>
      <Line points={ridgeLine} color="#2f7f8a" lineWidth={1} transparent opacity={0.55} />
      <Line points={edgeLineLeft} color="#1d5566" lineWidth={1} transparent opacity={0.4} />
      <Line points={edgeLineRight} color="#1d5566" lineWidth={1} transparent opacity={0.4} />
    </group>
  );
}

function StationRuler({ layout, showLabels }: { layout: SceneLayout; showLabels: boolean }) {
  const z = 8.2;
  const y = 0.025;
  const points = useMemo(
    () => [
      new THREE.Vector3(-layout.span / 2, y, z),
      new THREE.Vector3(layout.span / 2, y, z),
    ],
    [layout.span, z],
  );

  return (
    <group>
      <Line points={points} color="#2b425f" lineWidth={1} transparent opacity={0.85} />
      {layout.ticks.map((tick) => (
        <group key={tick.distance} position={[tick.position.x, y, z]}>
          <mesh>
            <boxGeometry args={[0.02, 0.01, 0.22]} />
            <meshBasicMaterial color="#3d5878" />
          </mesh>
          {showLabels ? (
            <SceneHtml position={[0, 0.08, 0.32]} center zIndexRange={[8, 0]}>
              <span className="numeric whitespace-nowrap text-[10px] tracking-wide text-mist-500">
                {tick.label}
              </span>
            </SceneHtml>
          ) : null}
        </group>
      ))}
    </group>
  );
}

function GroundPlane({ layout }: { layout: SceneLayout }) {
  return (
    <>
      <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, -0.015, 0]} receiveShadow>
        <planeGeometry args={[layout.span * 2.5, layout.span * 1.8]} />
        <meshStandardMaterial color="#060c16" roughness={0.98} metalness={0.02} />
      </mesh>
      <Grid
        position={[0, 0, 0]}
        args={[layout.span * 2.4, layout.span * 1.7]}
        cellSize={1}
        cellThickness={0.5}
        cellColor="#1c2c44"
        sectionSize={5}
        sectionThickness={0.9}
        sectionColor="#31506f"
        fadeDistance={layout.span * 2.2}
        fadeStrength={1.6}
        infiniteGrid={false}
        followCamera={false}
      />
    </>
  );
}

/** Renders the terrain, grid, landmark pins and station ruler under the pipeline. */
function LandmarkPins({ layout, showLabels }: { layout: SceneLayout; showLabels: boolean }) {
  if (!layout.landmarks || layout.landmarks.length === 0) return null;
  return (
    <group>
      {layout.landmarks.map((item) => {
        const { x, y, z } = item.position;
        return (
          <group key={item.landmark.id} position={[x, y, z]}>
            <Line
              points={[new THREE.Vector3(0, 0, 0), new THREE.Vector3(0, 0.9, 0)]}
              color={item.color}
              lineWidth={1.2}
              transparent
              opacity={0.75}
            />
            <mesh position={[0, 0.95, 0]}>
              <sphereGeometry args={[0.07, 10, 8]} />
              <meshBasicMaterial color={item.color} toneMapped={false} />
            </mesh>
            {showLabels ? (
              <SceneHtml position={[0, 1.24, 0]} center zIndexRange={[10, 0]}>
                <span
                  className="whitespace-nowrap rounded border border-line/60 bg-ink-950/80 px-1.5 py-0.5 text-[9.5px] text-mist-200 shadow"
                  style={{ borderLeftColor: item.color, borderLeftWidth: 2 }}
                >
                  {item.landmark.label}
                  {item.landmark.kp ? ` · KP ${item.landmark.kp}` : ""}
                </span>
              </SceneHtml>
            ) : null}
          </group>
        );
      })}
    </group>
  );
}

/** Arka planda kot farkını somutlaştıran yatay rakım kılavuz çizgileri. */
function ElevationBackdropGrid({
  layout,
  showLabels,
}: {
  layout: SceneLayout;
  showLabels: boolean;
}) {
  if (!layout.elevationTicks.length) return null;
  const halfX = layout.span / 2;
  const z = -7.2;

  return (
    <group>
      {layout.elevationTicks.map((tick) => (
        <group key={tick.elevation} position={[0, tick.y, z]}>
          <Line
            points={[new THREE.Vector3(-halfX, 0, 0), new THREE.Vector3(halfX, 0, 0)]}
            color="#223b54"
            lineWidth={1}
            transparent
            opacity={0.45}
          />
          {showLabels ? (
            <SceneHtml position={[-halfX - 0.55, 0, 0]} center zIndexRange={[6, 0]}>
              <span className="numeric whitespace-nowrap rounded bg-ink-950/70 px-1 py-0.5 text-[9px] text-mist-500">
                {tick.label}
              </span>
            </SceneHtml>
          ) : null}
        </group>
      ))}
    </group>
  );
}

export default function SceneEnvironment({
  layout,
  showLabels,
  showLandmarks,
  highQuality,
  reducedMotion,
}: SceneEnvironmentProps) {
  return (
    <group>
      <SceneLights layout={layout} highQuality={highQuality} />
      <GroundPlane layout={layout} />
      <Terrain layout={layout} />
      <ElevationBackdropGrid layout={layout} showLabels={showLabels} />
      {showLandmarks ? <LandmarkPins layout={layout} showLabels={showLabels} /> : null}
      <StationRuler layout={layout} showLabels={showLabels} />
      {highQuality && !reducedMotion ? (
        <ContactShadows
          position={[0, 0.012, 0]}
          scale={layout.span * 1.7}
          resolution={512}
          blur={2.4}
          opacity={0.4}
          far={layout.span * 0.45}
          frames={1}
          color="#000000"
        />
      ) : null}
    </group>
  );
}
