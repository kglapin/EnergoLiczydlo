import type { BuildingProject } from "./store"

export const NORMATIVE_SETTINGS_STORAGE_KEY = "energoliczydlo-normative-settings-v2"

export interface GroundElementSettings {
  exposed_perimeter_m?: number
  floor_thermal_resistance_m2k_w?: number
  basement_depth_m?: number
  periodic_amplitude_ratio?: number
  phase_shift_days?: number
  diagnostic_effective_depth_m?: number
}

export interface NormativeSettings {
  ground: {
    enabled: boolean
    certificate_mode: boolean
    soil_conductivity_w_mk?: number
    soil_density_kg_m3?: number
    soil_specific_heat_j_kgk?: number
    external_wall_thickness_m?: number
    elements: Record<string, GroundElementSettings>
  }
  heat_recovery: {
    enabled: boolean
    certificate_mode: boolean
    performance_source?: string
    efficiency_curve: Array<{ outdoor_temperature_c: number; efficiency: number }>
    summer_bypass_enabled: boolean
    bypass_min_outdoor_c?: number
    bypass_max_outdoor_c?: number
    bypass_indoor_margin_k: number
    frost_strategy: "none" | "preheater" | "reduce_recovery" | "disable_recovery"
    frost_exhaust_limit_c: number
    indoor_relative_humidity?: number
    preheater_max_power_w?: number
    preheater_efficiency: number
  }
  design_conditions: {
    enabled: boolean
    certificate_mode: boolean
    outdoor_design_temperature_c?: number
    source?: string
    heat_up_power_by_zone_w: Record<string, number>
    unheated_adjacent_temperature_by_element_c: Record<string, number>
    ground_adjacent_temperature_by_element_c: Record<string, number>
  }
  legal: {
    certificate_mode: boolean
    calculation_date?: string
    methodology_source?: string
    climate_data_source?: string
    primary_energy_factor_sources: Record<string, string>
  }
}

export const defaultNormativeSettings: NormativeSettings = {
  ground: {
    enabled: false,
    certificate_mode: false,
    elements: {},
  },
  heat_recovery: {
    enabled: false,
    certificate_mode: false,
    efficiency_curve: [],
    summer_bypass_enabled: false,
    bypass_indoor_margin_k: 1,
    frost_strategy: "none",
    frost_exhaust_limit_c: 0,
    preheater_efficiency: 1,
  },
  design_conditions: {
    enabled: false,
    certificate_mode: false,
    heat_up_power_by_zone_w: {},
    unheated_adjacent_temperature_by_element_c: {},
    ground_adjacent_temperature_by_element_c: {},
  },
  legal: {
    certificate_mode: false,
    primary_energy_factor_sources: {},
  },
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value)
}

function mergeSettings(value: unknown): NormativeSettings {
  if (!isRecord(value)) return structuredClone(defaultNormativeSettings)
  const ground = isRecord(value.ground) ? value.ground : {}
  const heatRecovery = isRecord(value.heat_recovery) ? value.heat_recovery : {}
  const design = isRecord(value.design_conditions) ? value.design_conditions : {}
  const legal = isRecord(value.legal) ? value.legal : {}
  return {
    ground: {
      ...defaultNormativeSettings.ground,
      ...ground,
      elements: isRecord(ground.elements)
        ? ground.elements as Record<string, GroundElementSettings>
        : {},
    },
    heat_recovery: {
      ...defaultNormativeSettings.heat_recovery,
      ...heatRecovery,
      efficiency_curve: Array.isArray(heatRecovery.efficiency_curve)
        ? heatRecovery.efficiency_curve as NormativeSettings["heat_recovery"]["efficiency_curve"]
        : [],
    },
    design_conditions: {
      ...defaultNormativeSettings.design_conditions,
      ...design,
      heat_up_power_by_zone_w: isRecord(design.heat_up_power_by_zone_w)
        ? design.heat_up_power_by_zone_w as Record<string, number>
        : {},
      unheated_adjacent_temperature_by_element_c: isRecord(
        design.unheated_adjacent_temperature_by_element_c,
      )
        ? design.unheated_adjacent_temperature_by_element_c as Record<string, number>
        : {},
      ground_adjacent_temperature_by_element_c: isRecord(
        design.ground_adjacent_temperature_by_element_c,
      )
        ? design.ground_adjacent_temperature_by_element_c as Record<string, number>
        : {},
    },
    legal: {
      ...defaultNormativeSettings.legal,
      ...legal,
      primary_energy_factor_sources: isRecord(legal.primary_energy_factor_sources)
        ? legal.primary_energy_factor_sources as Record<string, string>
        : {},
    },
  } as NormativeSettings
}

export function loadNormativeSettings(): NormativeSettings {
  if (typeof window === "undefined") return structuredClone(defaultNormativeSettings)
  const raw = window.localStorage.getItem(NORMATIVE_SETTINGS_STORAGE_KEY)
  if (!raw) return structuredClone(defaultNormativeSettings)
  try {
    return mergeSettings(JSON.parse(raw) as unknown)
  } catch {
    return structuredClone(defaultNormativeSettings)
  }
}

export function saveNormativeSettings(settings: NormativeSettings): void {
  if (typeof window === "undefined") return
  window.localStorage.setItem(NORMATIVE_SETTINGS_STORAGE_KEY, JSON.stringify(settings))
}

export function clearNormativeSettings(): void {
  if (typeof window === "undefined") return
  window.localStorage.removeItem(NORMATIVE_SETTINGS_STORAGE_KEY)
}

export function enrichProjectWithNormativeSettings(project: BuildingProject): BuildingProject {
  const settings = loadNormativeSettings()
  return {
    ...project,
    metadata: {
      ...(project.metadata ?? {}),
      normative: settings,
    },
  }
}
