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

export interface PolishCertificateMonthlySettings {
  enabled: boolean
  official_bip_climate_data: boolean
  monthly_outdoor_temperature_c: number[]
  solar_irradiation_kwh_m2_by_element: Record<string, number[]>
  heating_internal_temperature_c_by_zone: Record<string, number[]>
  cooling_internal_temperature_c_by_zone: Record<string, number[]>
  heating_gain_utilization_by_zone: Record<string, number[]>
  cooling_loss_utilization_by_zone: Record<string, number[]>
  beta_by_zone: Record<string, number[]>
  recovery_effectiveness_by_zone: Record<string, number[]>
  supply_extract_reduction_by_zone: Record<string, number[]>
  unheated_adjacent_temperature_c_by_element: Record<string, number[]>
  ground_adjacent_temperature_c_by_element: Record<string, number[]>
  internal_gain_density_w_m2_by_zone: Record<string, number>
  preheater_electricity_kwh_by_month: number[]
  heating_useful_override_kwh_by_zone: Record<string, number[]>
  cooling_useful_override_kwh_by_zone: Record<string, number[]>
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
  polish_certificate: PolishCertificateMonthlySettings
  legal: {
    certificate_mode: boolean
    calculation_date?: string
    methodology_source?: string
    climate_data_source?: string
    utilization_factor_source?: string
    ventilation_factor_source?: string
    primary_energy_factor_sources: Record<string, string>
  }
}

const defaultPolishCertificateSettings: PolishCertificateMonthlySettings = {
  enabled: false,
  official_bip_climate_data: false,
  monthly_outdoor_temperature_c: [],
  solar_irradiation_kwh_m2_by_element: {},
  heating_internal_temperature_c_by_zone: {},
  cooling_internal_temperature_c_by_zone: {},
  heating_gain_utilization_by_zone: {},
  cooling_loss_utilization_by_zone: {},
  beta_by_zone: {},
  recovery_effectiveness_by_zone: {},
  supply_extract_reduction_by_zone: {},
  unheated_adjacent_temperature_c_by_element: {},
  ground_adjacent_temperature_c_by_element: {},
  internal_gain_density_w_m2_by_zone: {},
  preheater_electricity_kwh_by_month: [],
  heating_useful_override_kwh_by_zone: {},
  cooling_useful_override_kwh_by_zone: {},
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
  polish_certificate: defaultPolishCertificateSettings,
  legal: {
    certificate_mode: false,
    primary_energy_factor_sources: {},
  },
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value)
}

function numberArray(value: unknown): number[] {
  return Array.isArray(value) && value.every((item) => typeof item === "number")
    ? value
    : []
}

function numberArrayMap(value: unknown): Record<string, number[]> {
  if (!isRecord(value)) return {}
  return Object.fromEntries(
    Object.entries(value)
      .filter(([, item]) => Array.isArray(item) && item.every((entry) => typeof entry === "number"))
      .map(([key, item]) => [key, item as number[]]),
  )
}

function numberMap(value: unknown): Record<string, number> {
  if (!isRecord(value)) return {}
  return Object.fromEntries(
    Object.entries(value).filter(([, item]) => typeof item === "number"),
  ) as Record<string, number>
}

function mergeCertificate(value: unknown): PolishCertificateMonthlySettings {
  const certificate = isRecord(value) ? value : {}
  return {
    ...defaultPolishCertificateSettings,
    ...certificate,
    monthly_outdoor_temperature_c: numberArray(certificate.monthly_outdoor_temperature_c),
    solar_irradiation_kwh_m2_by_element: numberArrayMap(
      certificate.solar_irradiation_kwh_m2_by_element,
    ),
    heating_internal_temperature_c_by_zone: numberArrayMap(
      certificate.heating_internal_temperature_c_by_zone,
    ),
    cooling_internal_temperature_c_by_zone: numberArrayMap(
      certificate.cooling_internal_temperature_c_by_zone,
    ),
    heating_gain_utilization_by_zone: numberArrayMap(
      certificate.heating_gain_utilization_by_zone,
    ),
    cooling_loss_utilization_by_zone: numberArrayMap(
      certificate.cooling_loss_utilization_by_zone,
    ),
    beta_by_zone: numberArrayMap(certificate.beta_by_zone),
    recovery_effectiveness_by_zone: numberArrayMap(certificate.recovery_effectiveness_by_zone),
    supply_extract_reduction_by_zone: numberArrayMap(
      certificate.supply_extract_reduction_by_zone,
    ),
    unheated_adjacent_temperature_c_by_element: numberArrayMap(
      certificate.unheated_adjacent_temperature_c_by_element,
    ),
    ground_adjacent_temperature_c_by_element: numberArrayMap(
      certificate.ground_adjacent_temperature_c_by_element,
    ),
    internal_gain_density_w_m2_by_zone: numberMap(
      certificate.internal_gain_density_w_m2_by_zone,
    ),
    preheater_electricity_kwh_by_month: numberArray(
      certificate.preheater_electricity_kwh_by_month,
    ),
    heating_useful_override_kwh_by_zone: numberArrayMap(
      certificate.heating_useful_override_kwh_by_zone,
    ),
    cooling_useful_override_kwh_by_zone: numberArrayMap(
      certificate.cooling_useful_override_kwh_by_zone,
    ),
  } as PolishCertificateMonthlySettings
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
    polish_certificate: mergeCertificate(value.polish_certificate),
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
