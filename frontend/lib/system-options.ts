export type SystemOption = {
  value: string
  label: string
  carrier: string
  generationEfficiency: number
  sinkTemperature?: number
}

/** Iloczyn sezonowych składowych sprawności systemu, używany jako η_tot. */
export function totalSystemEfficiency(system: {
  generation_efficiency?: unknown
  distribution_efficiency?: unknown
  storage_efficiency?: unknown
  control_efficiency?: unknown
}): number | null {
  const values = [
    system.generation_efficiency,
    system.distribution_efficiency,
    system.storage_efficiency,
    system.control_efficiency,
  ].map(Number)
  if (values.some((value) => !Number.isFinite(value) || value <= 0)) return null
  return values.reduce((product, value) => product * value, 1)
}

/**
 * Sprawność całkowita CWU ηW,tot = ηW,g · ηW,s · ηW,d · ηW,e.
 * Zwraca null, gdy któraś składowa jest nieprawidłowa (analogicznie do
 * totalSystemEfficiency dla ogrzewania/chłodzenia, ale z utilization_efficiency
 * zamiast control_efficiency).
 */
export function dhwTotalEfficiency(system: {
  generation_efficiency?: unknown
  storage_efficiency?: unknown
  distribution_efficiency?: unknown
  utilization_efficiency?: unknown
}): number | null {
  const values = [
    system.generation_efficiency,
    system.storage_efficiency,
    system.distribution_efficiency,
    system.utilization_efficiency,
  ].map(Number)
  if (values.some((value) => !Number.isFinite(value) || value <= 0)) return null
  return values.reduce((product, value) => product * value, 1)
}

/**
 * Normatywne obciążenie cieplne q_int [W/m²] z tabeli 26 rozporządzenia
 * w sprawie metodologii (Dz.U. 2015 poz. 376). Wiersze z β (udział czasu
 * użytkowania budynku) przyjmują β = 0,3 analogicznie do przykładu
 * standardowego dla budynków biurowych podanego w rozporządzeniu.
 */
export const normativeInternalGainWm2: Record<string, number> = {
  residential_single_family: 6.8,
  residential_multi_family_lump_sum: 7.1,
  residential_multi_family_individual_metering: 7.1,
  office: 5.7, // (20*0,6 + 8*0,4)*0,3 + (2*0,6 + 1*0,4)*0,7
  education: 4.3, // 12*β + 1*(1-β)
  healthcare: 8.0,
  retail_services: 3.7, // 10*β + 1*(1-β)
  collective_residential: 3.2, // 6*β + 2*(1-β)
  warehouse: 1.3, // 2*β + 1*(1-β)
}

const OCCUPANT_HEAT_W = 80 // W/osoba
const DEFAULT_OCCUPANCY_DENSITY = 0.03 // os./m² (domyślna gęstość strefy)

/** Podział normatywnego q_int na trzy źródła (osoby/światło/sprzęt). */
export function normativeInternalGains(
  buildingType: string,
  dhwUsageProfile: string,
  beta = 0.3,
) {
  const safeBeta = Math.min(1, Math.max(0, beta))
  const qInt =
    buildingType === "office"
      ? 15.2 * safeBeta + 1.6 * (1 - safeBeta)
      : buildingType === "school"
        ? 12 * safeBeta + 1 * (1 - safeBeta)
        : buildingType === "retail"
          ? 10 * safeBeta + 1 * (1 - safeBeta)
          : buildingType === "healthcare"
            ? 8
            : buildingType === "residential" &&
                dhwUsageProfile === "residential_multi_family_lump_sum"
              ? 7.1
              : buildingType === "residential" &&
                  dhwUsageProfile === "residential_multi_family_individual_metering"
                ? 7.1
                : normativeInternalGainWm2[dhwUsageProfile] ?? 6.8
  const occupancyPart = Math.min(qInt, OCCUPANT_HEAT_W * DEFAULT_OCCUPANCY_DENSITY)
  const remainder = qInt - occupancyPart
  return {
    occupancy: { power_density: OCCUPANT_HEAT_W },
    lighting: { power_density: Math.round(0.3 * remainder * 100) / 100 },
    equipment: { power_density: Math.round(0.7 * remainder * 100) / 100 },
    normative_power_density_w_m2: qInt,
  }
}

export const energyCarrierOptions = [
  { value: "electricity", label: "Energia elektryczna" },
  { value: "natural_gas", label: "Gaz ziemny" },
  { value: "lpg", label: "Gaz płynny" },
  { value: "heating_oil", label: "Olej opałowy" },
  { value: "hard_coal", label: "Węgiel kamienny" },
  { value: "lignite", label: "Węgiel brunatny" },
  { value: "biomass", label: "Biomasa" },
  { value: "biogas", label: "Biogaz" },
  { value: "district_heating", label: "Ciepło sieciowe" },
  { value: "solar", label: "Energia słoneczna" },
  { value: "wind", label: "Energia wiatrowa" },
  { value: "geothermal", label: "Energia geotermalna" },
]

export const heatingSourceOptions: SystemOption[] = [
  {
    value: "electric_direct",
    label: "Elektryczne ogrzewanie bezpośrednie",
    carrier: "electricity",
    generationEfficiency: 0.99,
  },
  {
    value: "gas_boiler",
    label: "Kocioł gazowy niskotemperaturowy (≤50 kW)",
    carrier: "natural_gas",
    generationEfficiency: 0.87,
    sinkTemperature: 55,
  },
  {
    value: "gas_condensing",
    label: "Kocioł gazowy kondensacyjny (55/45°C, ≤50 kW)",
    carrier: "natural_gas",
    generationEfficiency: 0.94,
    sinkTemperature: 35,
  },
  {
    value: "oil_boiler",
    label: "Kocioł na paliwo ciekłe (dane domyślne)",
    carrier: "heating_oil",
    generationEfficiency: 0.87,
    sinkTemperature: 55,
  },
  {
    value: "biomass_boiler",
    label: "Kocioł na biomasę automatyczny (≤100 kW)",
    carrier: "biomass",
    generationEfficiency: 0.7,
  },
  {
    value: "coal_boiler",
    label: "Kocioł węglowy (po 2000 r.)",
    carrier: "hard_coal",
    generationEfficiency: 0.82,
  },
  {
    value: "fireplace",
    label: "Kominek z zamkniętą komorą spalania",
    carrier: "biomass",
    generationEfficiency: 0.7,
  },
  {
    value: "heat_pump_air",
    label: "Pompa ciepła powietrze/woda (35/28°C)",
    carrier: "electricity",
    generationEfficiency: 3,
    sinkTemperature: 35,
  },
  {
    value: "heat_pump_ground",
    label: "Pompa ciepła glikol/woda (35/28°C)",
    carrier: "electricity",
    generationEfficiency: 4,
    sinkTemperature: 35,
  },
  {
    value: "heat_pump_water",
    label: "Pompa ciepła woda/woda (35/28°C)",
    carrier: "electricity",
    generationEfficiency: 4,
    sinkTemperature: 35,
  },
  {
    value: "district_heating",
    label: "Kompaktowy węzeł cieplny z obudową (≤100 kW)",
    carrier: "district_heating",
    generationEfficiency: 0.98,
  },
]

/**
 * Klasyfikacja instalacji odbiorczej. Pole opisuje sposób oddawania ciepła,
 * a nie źródło energii; nie ustawia automatycznie wartości ηH,d/ηH,e, bo ich
 * dobór zależy od rzeczywistego projektu instalacji i danych metodologii.
 * Backend wykorzystuje rozpoznane instalacje wodne do doboru pompy obiegowej
 * z tabeli 20, gdy energia pomocnicza nie została podana jawnie.
 */
export const heatingInstallationOptions = [
  { value: "water_radiators", label: "Ogrzewanie wodne z grzejnikami" },
  { value: "water_surface", label: "Ogrzewanie wodne płaszczyznowe (np. podłogowe)" },
  { value: "air_heating", label: "Ogrzewanie powietrzne" },
  { value: "electric_direct", label: "Ogrzewanie elektryczne bezpośrednie" },
  { value: "steam", label: "Ogrzewanie parowe" },
  { value: "other", label: "Inny rodzaj instalacji" },
]

export const dhwSourceOptions: SystemOption[] = [
  {
    value: "electric_storage",
    label: "Elektryczny podgrzewacz akumulacyjny",
    carrier: "electricity",
    generationEfficiency: 0.96,
  },
  {
    value: "electric_instantaneous",
    label: "Elektryczny podgrzewacz przepływowy",
    carrier: "electricity",
    generationEfficiency: 0.99,
  },
  {
    value: "gas_instantaneous",
    label: "Przepływowy podgrzewacz gazowy (zapłon elektryczny)",
    carrier: "natural_gas",
    generationEfficiency: 0.85,
  },
  {
    value: "gas_boiler",
    label: "Kocioł gazowy niskotemperaturowy (≤50 kW)",
    carrier: "natural_gas",
    generationEfficiency: 0.83,
  },
  {
    value: "gas_condensing",
    label: "Kocioł kondensacyjny gazowy/olejowy (≤50 kW)",
    carrier: "natural_gas",
    generationEfficiency: 0.85,
  },
  {
    value: "heat_pump_air",
    label: "Pompa ciepła powietrze/woda",
    carrier: "electricity",
    generationEfficiency: 2.6,
  },
  {
    value: "heat_pump_ground",
    label: "Pompa ciepła glikol/woda",
    carrier: "electricity",
    generationEfficiency: 3,
  },
  {
    value: "heat_pump_water",
    label: "Pompa ciepła woda/woda",
    carrier: "electricity",
    generationEfficiency: 3,
  },
  {
    value: "district_heating",
    label: "Kompaktowy węzeł cieplny z obudową (CO + CWU, ≤100 kW)",
    carrier: "district_heating",
    generationEfficiency: 0.97,
  },
]

export const coolingSourceOptions: SystemOption[] = [
  {
    value: "split_ac",
    label: "Klimatyzator split (R410A, <12 kW)",
    carrier: "electricity",
    generationEfficiency: 3.9,
  },
  {
    value: "multisplit_vrv",
    label: "System multisplit / VRV / VRF",
    carrier: "electricity",
    generationEfficiency: 4.1,
  },
  {
    value: "liquid_chiller_air",
    label: "Agregat wody lodowej, skraplacz powietrzny (scroll, R410A)",
    carrier: "electricity",
    generationEfficiency: 4,
  },
  {
    value: "liquid_chiller_water",
    label: "Agregat wody lodowej, skraplacz wodny (scroll, R410A)",
    carrier: "electricity",
    generationEfficiency: 5.6,
  },
  {
    value: "passive_ground_cooling",
    label: "Rewersyjna pompa ciepła z chłodzeniem pasywnym",
    carrier: "electricity",
    generationEfficiency: 10,
  },
  {
    value: "absorption_cooling",
    label: "Agregat absorpcyjny",
    carrier: "district_heating",
    generationEfficiency: 0.8,
  },
]

/** Klasyfikacja instalacji odbiorczej chłodu; nie zmienia automatycznie SEER. */
export const coolingInstallationOptions = [
  { value: "direct_expansion", label: "Chłodzenie bezpośrednie (DX, split, VRF/VRV)" },
  { value: "water_fan_coils", label: "Chłodzenie wodne z klimakonwektorami" },
  { value: "water_surface", label: "Chłodzenie wodne płaszczyznowe" },
  { value: "air_cooling", label: "Chłodzenie powietrzne" },
  { value: "passive", label: "Chłodzenie pasywne" },
  { value: "other", label: "Inny rodzaj instalacji" },
]

export const dhwDistributionOptions = [
  { value: "point_of_use", label: "Podgrzewanie bezpośrednio przy punkcie poboru", efficiency: 1 },
  { value: "single_dwelling", label: "Grupa punktów poboru w jednym lokalu", efficiency: 0.8 },
  { value: "central_no_circulation", label: "Centralne CWU bez cyrkulacji – budynek jednorodzinny", efficiency: 0.6 },
  { value: "central_circulation_uninsulated", label: "Centralne CWU z cyrkulacją, piony nieizolowane", efficiency: 0.6 },
  { value: "central_circulation_insulated", label: "Centralne CWU z cyrkulacją, instalacja izolowana", efficiency: 0.7 },
  { value: "central_circulation_time_limited", label: "Centralne CWU z cyrkulacją ograniczoną czasowo", efficiency: 0.8 },
]
