import { create } from "zustand"
import { persist } from "zustand/middleware"

export interface BuildingProject {
  version: string
  project_name: string
  metadata?: Record<string, unknown>
  general: {
    building_name: string
    building_type: string
    dhw_usage_profile: string
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
    height: number
    width: number
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
    height: number
    width: number
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
    operation_mode?: string
    airflow_rate: number
    heat_recovery_efficiency: number
    infiltration_rate: number
    fan_infiltration_rate?: number
    usage_share_beta?: number
    supply_temperature?: number
    mechanical_fan_power?: number
    schedule?: {
      type: string
      constant_value?: number
      weekday?: number[]
      saturday?: number[]
      sunday?: number[]
      holiday?: number[]
    } | null
  }
  internal_gains?: {
    occupancy: { power_density: number; schedule?: BuildingProject["ventilation"]["schedule"] }
    lighting: { power_density: number; schedule?: BuildingProject["ventilation"]["schedule"] }
    equipment: { power_density: number; schedule?: BuildingProject["ventilation"]["schedule"] }
    normative_power_density_w_m2?: number
  }
  systems?: {
    heating: {
      system_type: string
      installation_type?: string
      fuel_or_carrier: string
      nominal_power?: number
      generation_efficiency?: number
      distribution_efficiency?: number
      storage_efficiency?: number
      control_efficiency?: number
      sink_temperature?: number
      auxiliary_energy_kwh_year?: number
    }
    cooling?: {
      system_type: string
      installation_type?: string
      fuel_or_carrier: string
      generation_efficiency?: number
      distribution_efficiency?: number
      storage_efficiency?: number
      control_efficiency?: number
      auxiliary_energy_kwh_year?: number
    }
    dhw: {
      system_type: string
      fuel_or_carrier: string
      generation_efficiency?: number
      storage_efficiency?: number
      distribution_efficiency?: number
      utilization_efficiency?: number
      distribution_type?: string
    }
  }
  primary_energy?: Record<string, unknown>
}

export interface CalculationResult {
  project_id: string
  status: string
  design_heating_power_kw?: number
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

export interface HistoryItem {
  id: string
  project_name: string
  building_name: string
  eu: number | null
  ek: number | null
  ep: number | null
  savedAt: string
  project: BuildingProject
  result: CalculationResult | null
}

interface AppState {
  project: BuildingProject | null
  result: CalculationResult | null
  history: HistoryItem[]
  activeHistoryId: string | null
  setProject: (project: BuildingProject) => void
  setResult: (result: CalculationResult | null) => void
  autoSaveProject: (project: BuildingProject) => string
  addToHistory: () => void
  loadHistoryItem: (id: string) => void
  removeHistoryItem: (id: string) => void
  startNewProject: () => void
  reset: () => void
}

const initialState = {
  project: null,
  result: null,
  history: [],
  activeHistoryId: null,
}

function createDraftId() {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) {
    return `draft-${crypto.randomUUID()}`
  }
  return `draft-${Date.now()}-${Math.random().toString(36).slice(2)}`
}

export const useAppStore = create<AppState>()(
  persist(
    (set, get) => ({
      ...initialState,
      setProject: (project) => set({ project }),
      setResult: (result) => set({ result }),
      autoSaveProject: (project) => {
        const { activeHistoryId, history, result } = get()
        const id = activeHistoryId ?? createDraftId()
        const previousItem = history.find((item) => item.id === id)
        const savedResult = result ?? previousItem?.result ?? null
        const item: HistoryItem = {
          id,
          project_name: project.project_name,
          building_name: project.general.building_name,
          eu: savedResult?.annual_indicators.eu_kwh_m2_year ?? previousItem?.eu ?? null,
          ek: savedResult?.annual_indicators.ek_kwh_m2_year ?? previousItem?.ek ?? null,
          ep: savedResult?.annual_indicators.ep_kwh_m2_year ?? previousItem?.ep ?? null,
          savedAt: new Date().toISOString(),
          project,
          result: savedResult,
        }
        set((state) => ({
          project,
          history: [item, ...state.history.filter((historyItem) => historyItem.id !== id)],
          activeHistoryId: id,
        }))
        return id
      },
      addToHistory: () => {
        const { project, result, activeHistoryId } = get()
        if (!project || !result) return
        const item: HistoryItem = {
          id: activeHistoryId ?? result.project_id,
          project_name: project.project_name,
          building_name: project.general.building_name,
          eu: result.annual_indicators.eu_kwh_m2_year,
          ek: result.annual_indicators.ek_kwh_m2_year,
          ep: result.annual_indicators.ep_kwh_m2_year,
          savedAt: new Date().toISOString(),
          project,
          result,
        }
        set((state) => ({
          history: [item, ...state.history.filter((h) => h.id !== item.id)],
          activeHistoryId: item.id,
        }))
      },
      loadHistoryItem: (id) => {
        const item = get().history.find((h) => h.id === id)
        if (item) {
          set({ project: item.project, result: item.result, activeHistoryId: item.id })
        }
      },
      removeHistoryItem: (id) => {
        set((state) => ({
          history: state.history.filter((h) => h.id !== id),
          activeHistoryId: state.activeHistoryId === id ? null : state.activeHistoryId,
        }))
      },
      startNewProject: () => set({ project: null, result: null, activeHistoryId: null }),
      reset: () => set(initialState),
    }),
    {
      name: "energoliczydlo-store",
    }
  )
)
