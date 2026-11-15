import {
  Component,
  useMemo,
  type ReactNode,
} from "react";
import { Canvas } from "@react-three/fiber";
import { PerspectiveCamera } from "@react-three/drei";
import * as THREE from "three";
import type { SceneData } from "../../lib/scene";
import SceneEnvironment from "./SceneEnvironment";
import PipeNetwork from "./PipeNetwork";
import SceneEquipment from "./SceneEquipment";
import PipelinePig, { FlowParticles, type PigHandle } from "./PigAndFlow";
import SceneCamera, { type CameraRequest } from "./SceneCamera";
import type {
  ColorMode,
  LayoutEquipment,
  SceneLayout,
} from "./sceneModel";

interface SceneCanvasProps {
  scene: SceneData;
  layout: SceneLayout;
  clipPlane: THREE.Plane;
  clipPlanes: THREE.Plane[];
  colorMode: ColorMode;
  selectedId: string | null;
  onSelect: (id: string | null) => void;
  showLabels: boolean;
  showFlow: boolean;
  cutaway: boolean;
  cameraRequest: CameraRequest;
  focusEquipment: LayoutEquipment | null;
  pigPlaying: boolean;
  pigRate: number;
  pigStart: number;
  pigPositionRef: PigHandle;
  reducedMotion: boolean;
  compact: boolean;
  visible: boolean;
  fallback: ReactNode;
}

interface SceneErrorBoundaryState {
  failed: boolean;
}

class SceneErrorBoundary extends Component<
  { fallback: ReactNode; children: ReactNode },
  SceneErrorBoundaryState
> {
  state: SceneErrorBoundaryState = { failed: false };

  static getDerivedStateFromError(): SceneErrorBoundaryState {
    return { failed: true };
  }

  render() {
    if (this.state.failed) return this.props.fallback;
    return this.props.children;
  }
}

const CAMERA_FOV = 38;
const CAMERA_FOV_COMPACT = 44;

export default function SceneCanvas({
  scene,
  layout,
  clipPlane,
  clipPlanes,
  colorMode,
  selectedId,
  onSelect,
  showLabels,
  showFlow,
  cutaway,
  cameraRequest,
  focusEquipment,
  pigPlaying,
  pigRate,
  pigStart,
  pigPositionRef,
  reducedMotion,
  compact,
  visible,
  fallback,
}: SceneCanvasProps) {
  const dpr: number | [number, number] = compact ? 1.4 : [1, 2];
  const gl = useMemo(
    () => ({
      antialias: !compact,
      alpha: false,
      stencil: false,
      powerPreference: "high-performance" as const,
    }),
    [compact],
  );
  const overview = layout.views.overview.position;

  return (
    <SceneErrorBoundary fallback={fallback}>
      <Canvas
        className="h-full w-full"
        dpr={dpr}
        shadows={compact ? false : "percentage"}
        gl={gl}
        frameloop={visible ? "always" : "never"}
        camera={{ fov: CAMERA_FOV, near: 0.08, far: layout.span * 9 }}
        onPointerMissed={() => onSelect(null)}
        onCreated={({ gl: renderer }) => {
          renderer.localClippingEnabled = true;
          renderer.toneMappingExposure = 1.05;
        }}
      >
        <PerspectiveCamera
          makeDefault
          fov={compact ? CAMERA_FOV_COMPACT : CAMERA_FOV}
          near={0.08}
          far={layout.span * 9}
          position={[overview.x, overview.y, overview.z]}
        />
        <color attach="background" args={["#070b14"]} />
        <fog attach="fog" args={["#070b14", layout.span * 1.15, layout.span * 3.4]} />

        <SceneEnvironment
          layout={layout}
          showLabels={showLabels}
          highQuality={!compact}
          reducedMotion={reducedMotion}
        />

        <PipeNetwork
          layout={layout}
          clipPlanes={clipPlanes}
          colorMode={colorMode}
          selectedId={selectedId}
          onSelect={onSelect}
          showLabels={showLabels}
        />

        <SceneEquipment
          layout={layout}
          selectedId={selectedId}
          onSelect={onSelect}
          showLabels={showLabels}
        />

        <PipelinePig
          layout={layout}
          startDistance={pigStart}
          speedMps={scene.pig?.speed_m_per_s ?? null}
          playing={pigPlaying}
          rate={pigRate}
          visible={Boolean(scene.pig)}
          showLabels={showLabels}
          reducedMotion={reducedMotion}
          positionRef={pigPositionRef}
        />

        <FlowParticles
          layout={layout}
          speedMps={scene.flow_speed_m_per_s}
          enabled={showFlow}
          reducedMotion={reducedMotion}
          compact={compact}
        />

        <SceneCamera
          layout={layout}
          request={cameraRequest}
          focusEquipment={focusEquipment}
          pigHandle={pigPositionRef}
          reducedMotion={reducedMotion}
          clipPlane={clipPlane}
          cutaway={cutaway}
        />
      </Canvas>
    </SceneErrorBoundary>
  );
}
