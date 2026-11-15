import { useEffect, useMemo, useRef, type ComponentRef } from "react";
import { OrbitControls } from "@react-three/drei";
import { useFrame, useThree } from "@react-three/fiber";
import * as THREE from "three";
import type { CameraPreset, LayoutEquipment, SceneLayout } from "./sceneModel";
import type { PigHandle } from "./PigAndFlow";

export interface CameraRequest {
  preset: CameraPreset;
  nonce: number;
}

interface SceneCameraProps {
  layout: SceneLayout;
  request: CameraRequest;
  focusEquipment: LayoutEquipment | null;
  pigHandle: PigHandle;
  reducedMotion: boolean;
  clipPlane: THREE.Plane;
  cutaway: boolean;
}

type OrbitControlsHandle = ComponentRef<typeof OrbitControls>;

interface View {
  position: THREE.Vector3;
  target: THREE.Vector3;
}

function viewFor(
  preset: CameraPreset,
  layout: SceneLayout,
  focus: LayoutEquipment | null,
  pigHandle: PigHandle,
  pigOffset: THREE.Vector3,
): View {
  switch (preset) {
    case "profile":
      return {
        position: layout.views.profile.position.clone(),
        target: layout.views.profile.target.clone(),
      };
    case "top":
      return {
        position: layout.views.top.position.clone(),
        target: layout.views.top.target.clone(),
      };
    case "pig": {
      const target = pigHandle.current.clone();
      return {
        position: target.clone().add(pigOffset),
        target,
      };
    }
    case "equipment": {
      const target = focus
        ? focus.pipePoint.clone().add(new THREE.Vector3(0, 0.35, 0))
        : layout.center.clone();
      return {
        position: target.clone().add(new THREE.Vector3(2.4, 1.8, 4.1)),
        target,
      };
    }
    default:
      return {
        position: layout.views.overview.position.clone(),
        target: layout.views.overview.target.clone(),
      };
  }
}

/** Smooth camera presets plus orbit controls, clipped to stay above the ground. */
export default function SceneCamera({
  layout,
  request,
  focusEquipment,
  pigHandle,
  reducedMotion,
  clipPlane,
  cutaway,
}: SceneCameraProps) {
  const controlsRef = useRef<OrbitControlsHandle>(null);
  const transitionRef = useRef<View | null>(null);
  const followRef = useRef(false);
  const lastPig = useRef(new THREE.Vector3());
  const pigDelta = useRef(new THREE.Vector3());
  const camera = useThree((state) => state.camera);
  const pigOffset = useMemo(
    () => new THREE.Vector3(layout.span * 0.09, layout.span * 0.17, layout.span * 0.3),
    [layout.span],
  );

  useEffect(() => {
    const controls = controlsRef.current;
    if (controls) {
      controls.target.set(layout.center.x, layout.center.y, 0);
      controls.update();
    }
    followRef.current = request.preset === "pig";
    lastPig.current.copy(pigHandle.current);
    transitionRef.current = viewFor(
      request.preset,
      layout,
      focusEquipment,
      pigHandle,
      pigOffset,
    );
    // `request.nonce` is the trigger; layout/focus are read from this render.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [request.nonce]);

  useFrame((_, delta) => {
    const controls = controlsRef.current;
    if (!controls) return;

    if (followRef.current) {
      const pig = pigHandle.current;
      if (transitionRef.current) {
        transitionRef.current.target.copy(pig);
        transitionRef.current.position.copy(pig).add(pigOffset);
      } else {
        pigDelta.current.copy(pig).sub(lastPig.current);
        camera.position.add(pigDelta.current);
        controls.target.add(pigDelta.current);
        controls.update();
      }
      lastPig.current.copy(pig);
    }

    const transition = transitionRef.current;
    if (!transition) return;

    if (reducedMotion) {
      camera.position.copy(transition.position);
      controls.target.copy(transition.target);
      controls.update();
      transitionRef.current = null;
      return;
    }

    const alpha = 1 - Math.exp(-Math.max(0.001, Math.min(delta, 0.08)) * 5.2);
    camera.position.lerp(transition.position, alpha);
    controls.target.lerp(transition.target, alpha);
    controls.update();

    if (
      camera.position.distanceTo(transition.position) < 0.02 &&
      controls.target.distanceTo(transition.target) < 0.02
    ) {
      transitionRef.current = null;
    }
  });

  // Keep the section plane opening toward the viewer.
  useFrame(({ camera: currentCamera }) => {
    if (!cutaway) return;
    clipPlane.normal.set(0, 0, currentCamera.position.z >= 0 ? -1 : 1);
    clipPlane.constant = 0;
  });

  return (
    <OrbitControls
      ref={controlsRef}
      makeDefault
      enableDamping
      dampingFactor={0.075}
      rotateSpeed={0.72}
      zoomSpeed={0.85}
      panSpeed={0.72}
      minDistance={0.6}
      maxDistance={layout.span * 2.6}
      maxPolarAngle={Math.PI * 0.495}
      onStart={() => {
        transitionRef.current = null;
        followRef.current = false;
      }}
    />
  );
}
