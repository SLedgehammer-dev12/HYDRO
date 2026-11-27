import { useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { SceneHtml } from "./SceneHtml";
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
  type SceneViewMode,
} from "./sceneModel";

interface PipeNetworkProps {
  layout: SceneLayout;
  mode?: SceneViewMode;
  translucentPipe?: boolean;
  clipPlanes: THREE.Plane[];
  colorMode: ColorMode;
  selectedId: string | null;
  onSelect: (id: string | null) => void;
  onSelectSection?: (sessionId: string) => void;
  showLabels: boolean;
}

interface PipeSegmentProps {
  item: LayoutSegment;
  index: number;
  totalSegments: number;
  mode: SceneViewMode;
  translucentPipe: boolean;
  isSectionLabelPivot: boolean;
  isSectionBoundaryStart: boolean;
  prevOd?: number;
  nextOd?: number;
  colorMode: ColorMode;
  layout: SceneLayout;
  clipPlanes: THREE.Plane[];
  selected: boolean;
  sectionHovered: boolean;
  onHoverChange: (hovered: boolean, segment: SceneSegment) => void;
  showLabels: boolean;
  onSelect: (id: string | null) => void;
  onSelectSection?: (sessionId: string) => void;
}

function SegmentTooltip({
  segment,
  isOverview,
}: {
  segment: SceneSegment;
  isOverview: boolean;
}) {
  return (
    <div className="w-[208px] rounded-lg border border-line/80 bg-ink-950/95 px-2.5 py-2 shadow-xl">
      <div className="flex items-center justify-between gap-2">
        <span className="text-[11px] font-semibold text-mist-100">
          {isOverview && segment.section_no ? segment.section_no : segment.label}
        </span>
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
      {isOverview && segment.session_id ? (
        <p className="mt-1.5 border-t border-line/50 pt-1 text-[9.5px] font-medium text-cyan">
          Detay 3D &amp; Pig akışı için tıklayın →
        </p>
      ) : null}
    </div>
  );
}

function PipeSegment({
  item,
  index,
  totalSegments,
  mode,
  translucentPipe,
  isSectionLabelPivot,
  isSectionBoundaryStart,
  prevOd,
  nextOd,
  colorMode,
  layout,
  clipPlanes,
  selected,
  sectionHovered,
  onHoverChange,
  showLabels,
  onSelect,
  onSelectSection,
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
  const isHighlighted = selected || sectionHovered || hovered;
  const emissiveIntensity = selected ? 0.55 : sectionHovered || hovered ? 0.34 : 0.05;
  const denseTopo = totalSegments > 6;
  const isOverview = mode === "overview";
  const showStartFlange = isOverview
    ? isSectionBoundaryStart
    : !denseTopo ||
      index === 0 ||
      (typeof prevOd === "number" && Math.abs(prevOd - segment.outside_diameter_mm) > 0.1);
  const showEndFlange = isOverview
    ? index === totalSegments - 1
    : !denseTopo ||
      index === totalSegments - 1 ||
      (typeof nextOd === "number" && Math.abs(nextOd - segment.outside_diameter_mm) > 0.1);
  const showWeldBall = denseTopo && index > 0 && !showStartFlange;
  const showSegmentLabel = isOverview
    ? showLabels && !hovered && isSectionLabelPivot
    : showLabels && !hovered && !denseTopo;
  const overviewLabelText = segment.section_no || segment.label.split("·")[0]?.trim() || segment.label;

  useEffect(() => {
    return () => {
      document.body.style.cursor = "";
    };
  }, []);

  if (length < 1e-4) return null;

  const handleOver = (event: { stopPropagation: () => void }) => {
    event.stopPropagation();
    setHovered(true);
    onHoverChange(true, segment);
    document.body.style.cursor = "pointer";
  };
  const handleOut = () => {
    setHovered(false);
    onHoverChange(false, segment);
    document.body.style.cursor = "";
  };

  return (
    <group position={mid}>
      <group quaternion={quaternion}>
        <mesh
          castShadow={!translucentPipe}
          receiveShadow={!translucentPipe}
          renderOrder={translucentPipe ? 4 : 0}
          onPointerOver={handleOver}
          onPointerOut={handleOut}
          onClick={(event) => {
            event.stopPropagation();
            if (isOverview && segment.session_id && onSelectSection) {
              onSelectSection(segment.session_id);
              return;
            }
            onSelect(selected ? null : segment.id);
          }}
        >
          <cylinderGeometry args={[radius, radius, length, 20, 1, false]} />
          <meshStandardMaterial
            color={color}
            metalness={translucentPipe ? 0.22 : 0.38}
            roughness={translucentPipe ? 0.18 : 0.42}
            emissive={isHighlighted ? "#22d3ee" : color}
            emissiveIntensity={emissiveIntensity}
            transparent={translucentPipe}
            opacity={translucentPipe ? 0.3 : 1}
            depthWrite={!translucentPipe}
            clippingPlanes={clipPlanes}
            clipShadows={!translucentPipe}
          />
        </mesh>

        {/* Interior wall. Revealed by cutaway or translucent view. */}
        <mesh renderOrder={translucentPipe ? 3 : 0}>
          <cylinderGeometry args={[innerRadius, innerRadius, length * 0.998, 20, 1, true]} />
          <meshStandardMaterial
            color={innerColor}
            metalness={0.55}
            roughness={0.48}
            side={THREE.BackSide}
            emissive={color}
            emissiveIntensity={0.12}
            transparent={translucentPipe}
            opacity={translucentPipe ? 0.16 : 1}
            depthWrite={!translucentPipe}
            clippingPlanes={clipPlanes}
          />
        </mesh>

        {showWeldBall ? (
          <mesh position={[0, -length * 0.5, 0]} castShadow={!translucentPipe}>
            <sphereGeometry args={[radius * 1.02, 14, 10]} />
            <meshStandardMaterial
              color={color}
              metalness={0.42}
              roughness={0.4}
              transparent={translucentPipe}
              opacity={translucentPipe ? 0.28 : 1}
              depthWrite={!translucentPipe}
              clippingPlanes={clipPlanes}
            />
          </mesh>
        ) : null}

        {[start, end].map((_point, endpointIdx) => {
          const showFlange = endpointIdx === 0 ? showStartFlange : showEndFlange;
          if (!showFlange) return null;
          const boundaryAccent = isOverview && isSectionBoundaryStart && endpointIdx === 0;
          return (
            <group key={endpointIdx} position={[0, (endpointIdx === 0 ? -1 : 1) * length * 0.5, 0]}>
              <mesh castShadow={!translucentPipe} rotation={[0, 0, 0]}>
                <cylinderGeometry
                  args={[
                    radius * (boundaryAccent ? 1.38 : 1.16),
                    radius * (boundaryAccent ? 1.38 : 1.16),
                    boundaryAccent ? 0.045 : 0.055,
                    20,
                    1,
                    false,
                  ]}
                />
                <meshStandardMaterial
                  color={boundaryAccent ? "#38bdf8" : "#8aa2bb"}
                  emissive={boundaryAccent ? "#22d3ee" : "#000000"}
                  emissiveIntensity={boundaryAccent ? 0.35 : 0}
                  metalness={0.75}
                  roughness={0.34}
                  clippingPlanes={clipPlanes}
                />
              </mesh>
              <mesh>
                <torusGeometry args={[radius * (boundaryAccent ? 1.4 : 1.16), 0.012, 6, 24]} />
                <meshStandardMaterial
                  color={boundaryAccent ? "#67e8f9" : "#c7d7e6"}
                  metalness={0.8}
                  roughness={0.3}
                  clippingPlanes={clipPlanes}
                />
              </mesh>
            </group>
          );
        })}

        {selected ? (
          <mesh rotation={[-Math.PI / 2, 0, 0]}>
            <torusGeometry args={[radius * 1.38, 0.016, 6, 32]} />
            <meshBasicMaterial color="#22d3ee" toneMapped={false} />
          </mesh>
        ) : null}
      </group>

      {showSegmentLabel ? (
        <SceneHtml
          position={[0, radius + 0.34, 0]}
          center
          zIndexRange={[12, 0]}
        >
          <span
            className="numeric whitespace-nowrap rounded border border-line/60 bg-ink-950/80 px-1.5 py-0.5 text-[10px] font-semibold text-mist-100 shadow"
            style={{ borderLeftColor: meta.color, borderLeftWidth: 2 }}
          >
            {isOverview ? overviewLabelText : segment.label}
          </span>
        </SceneHtml>
      ) : null}

      {hovered ? (
        <SceneHtml
          position={[0, radius + 0.55, 0]}
          center
          zIndexRange={[24, 12]}
        >
          <SegmentTooltip segment={segment} isOverview={isOverview} />
        </SceneHtml>
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
  mode = "detail",
  translucentPipe = false,
  clipPlanes,
  colorMode,
  selectedId,
  onSelect,
  onSelectSection,
  showLabels,
}: PipeNetworkProps) {
  const [hoveredSessionId, setHoveredSessionId] = useState<string | null>(null);

  const sectionMeta = useMemo(() => {
    const counts = new Map<string, number>();
    const seen = new Map<string, number>();
    const pivots = new Set<number>();
    const boundaries = new Set<number>();

    layout.segments.forEach((item, idx) => {
      const key = item.segment.session_id || item.segment.section_no || item.segment.id;
      counts.set(key, (counts.get(key) ?? 0) + 1);
      const prevKey =
        idx > 0
          ? layout.segments[idx - 1].segment.session_id ||
            layout.segments[idx - 1].segment.section_no ||
            layout.segments[idx - 1].segment.id
          : null;
      if (idx === 0 || prevKey !== key) {
        boundaries.add(idx);
      }
    });

    layout.segments.forEach((item, idx) => {
      const key = item.segment.session_id || item.segment.section_no || item.segment.id;
      const cur = seen.get(key) ?? 0;
      seen.set(key, cur + 1);
      const total = counts.get(key) ?? 1;
      if (cur === Math.floor(total / 2)) {
        pivots.add(idx);
      }
    });

    return { pivots, boundaries };
  }, [layout.segments]);

  const handleHoverChange = (hovered: boolean, seg: SceneSegment) => {
    if (!seg.session_id) {
      if (!hovered) setHoveredSessionId(null);
      return;
    }
    setHoveredSessionId(hovered ? seg.session_id : null);
  };

  return (
    <group>
      <PipeSupports layout={layout} />
      {layout.segments.map((item, idx) => (
        <PipeSegment
          key={item.segment.id}
          item={item}
          index={idx}
          totalSegments={layout.segments.length}
          mode={mode}
          translucentPipe={translucentPipe}
          isSectionLabelPivot={sectionMeta.pivots.has(idx)}
          isSectionBoundaryStart={sectionMeta.boundaries.has(idx)}
          prevOd={idx > 0 ? layout.segments[idx - 1].segment.outside_diameter_mm : undefined}
          nextOd={
            idx < layout.segments.length - 1
              ? layout.segments[idx + 1].segment.outside_diameter_mm
              : undefined
          }
          colorMode={colorMode}
          layout={layout}
          clipPlanes={clipPlanes}
          selected={selectedId === item.segment.id}
          sectionHovered={
            Boolean(hoveredSessionId) && item.segment.session_id === hoveredSessionId
          }
          onHoverChange={handleHoverChange}
          showLabels={showLabels}
          onSelect={onSelect}
          onSelectSection={onSelectSection}
        />
      ))}
    </group>
  );
}
