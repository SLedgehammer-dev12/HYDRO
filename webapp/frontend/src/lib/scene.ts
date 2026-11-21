export type ScenePoint = [number, number];

export type SceneStatus = "pending" | "pass" | "fail" | "warning";

export interface SceneSegment {
  id: string;
  session_id?: string;
  section_no?: string;
  label: string;
  /** Start/end distance along the pipeline in metres. */
  start_m: number;
  end_m: number;
  /** Start/end elevation in metres. */
  start_elevation_m: number;
  end_elevation_m: number;
  outside_diameter_mm: number;
  wall_thickness_mm: number;
  grade?: string | null;
  smys_mpa?: number | null;
  pressure_at_100_smys_bar?: number | null;
  pressure_bar?: number;
  utilization?: number;
  status?: SceneStatus;
}

export type SceneEquipmentType =
  | "valve"
  | "pump"
  | "test-head"
  | "pig-launcher"
  | "pig-receiver"
  | "gauge";

export interface SceneEquipment {
  id: string;
  type: SceneEquipmentType;
  label: string;
  distance_m: number;
  elevation_m: number;
  status?: SceneStatus;
}

export interface ScenePig {
  distance_m: number;
  elevation_m?: number;
  progress?: number;
  speed_m_per_s?: number;
}

export interface SceneLandmark {
  id: string;
  distance_m: number;
  elevation_m: number;
  kp?: string;
  kind: string;
  label: string;
}

export interface SceneData {
  segments: SceneSegment[];
  equipment: SceneEquipment[];
  pig?: ScenePig | null;
  flow_speed_m_per_s?: number;
  pressure_min_bar?: number;
  pressure_max_bar?: number;
  start_kp_m?: number | null;
  is_survey_profile?: boolean;
  is_custom_equipment?: boolean;
  /** Optional real survey points: [distance_m, elevation_m]. */
  profile_points?: ScenePoint[];
  landmarks?: SceneLandmark[];
  warnings?: string[];
}
