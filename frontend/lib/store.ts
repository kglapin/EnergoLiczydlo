import { create } from "zustand"
import { persist } from "zustand/middleware"

export interface BuildingProject {
  version: string
  project_name: string
  metadata?: Record<string, unknown>
  general: {
    building_name: string
    building_type: string
    construction_year: number
    conditioned_floor_area: number
    usable_floor_area: number
    heated_volume: number
    number_of_storeys: number
    location_address?: string
  }
  climate_station_id: string
  thermal_zones: Array<{
    id: string
    name: string
    zone_type: string
    floor_area: number
    volume: number
    setpoint_heating: number
    setpoint_cooling?: number
    occupancy_density: number
  }>
  opaque_building_elements: Array<{
    id: string
    name: string
    zone_id: string
    element_type: string
    orientation_azimuth: number
    inclination: number
    area: number
    u_value: number
    solar_absorptance?: number
    emissivity?: number
    adjacent_space_type?: string
    adjacent_temperature?: number
  }>
  transparent_building_elements: Array<{
    id: string
    name: string
    zone_id: string
    element_type: string
    orientation_azimuth: number
    inclination: number
    area: number
    u_value: number
    g_value: number
    frame_factor?: number
    shading_factor?: number
  }>
  thermal_bridges?: {
    auto_calculate: boolean
    linear_bridges: unknown[]
    point_bridges: unknown[]
  }
  ventilation: {
    ventilation_type: string
    airflow_rate: number
    heat_recovery_efficiency: number
    infiltration_rate: number
    supply_temperature?: number
    mechanical_fan_power?: number
  }
  internal_gains?: {
    occupancy: { power_density: number }
    lighting: { power_density: number }
    equipment: { power_density: number }
  }
  systems?: Record<string, unknown>
  primary_energy?: Record<string, unknown>
}

export interface CalculationResult {
  project_id: string
  status: string
  annual_indicators: {
    eu_kwh_m2_year: number
    ek_kwh_m2_year: number
    ep_kwh_m2_year: number
    ec_tco2_m2_year: number
    u_oze_percent: number
    heating_kwh_m2_year: number
    cooling_kwh_m2_year: number
    dhw_kwh_m2_year: number
  }
  monthly: Array<{
    month: number
    heating_kwh: number
    cooling_kwh: number
    dhw_kwh: number
    internal_gains_kwh: number
    solar_gains_kwh: number
    transmission_losses_kwh: number
    ventilation_losses_kwh: number
  }>
  compliance: Array<{
    name: string
    passed: boolean
    message: string
  }>
}

interface AppState {
  project: BuildingProject | null
  result: CalculationResult | null
  setProject: (project: BuildingProject) => void
  setResult: (result: CalculationResult | null) => void
  reset: () => void
}

const initialState = {
  project: null,
  result: null,
}

export const useAppStore = create<AppState>()(
  persist(
    (set) => ({
      ...initialState,
      setProject: (project) => set({ project }),
      setResult: (result) => set({ result }),
      reset: () => set(initialState),
    }),
    {
      name: "energoliczydlo-store",
    }
  )
)
