# Normatywny model godzinowy v2

## Cel

Ta warstwa rozszerza roczny solver 5R1C o dane i kontrole potrzebne do
charakterystyki energetycznej w modelu godzinowym oraz o odrębne obliczenie
projektowego obciążenia cieplnego.

Najważniejsza zasada architektoniczna pozostaje bez zmian:

- `Eu`, `Ek` i `Ep` wynikają z bilansu 8760 godzin,
- projektowe obciążenie cieplne jest wynikiem wymiarującym i **nie jest**
  dodawane do rocznego `Eu`,
- brak danych wymaganych do trybu formalnego nie jest zastępowany wartością
  domyślną.

## Podstawa metodologiczna

Projekt jest budowany wokół następujących dokumentów i zakresów:

- rozporządzenie Ministra Infrastruktury i Rozwoju z 27 lutego 2015 r. w
  sprawie metodologii wyznaczania charakterystyki energetycznej budynku lub
  części budynku oraz świadectw charakterystyki energetycznej, z późniejszymi
  zmianami,
- PN-EN ISO 52016-1 — godzinowe zapotrzebowanie na ogrzewanie i chłodzenie,
  temperatury wewnętrzne i obciążenia cieplne,
- PN-EN ISO 13370 — wymiana ciepła przez grunt,
- PN-EN 12831-1 — projektowe obciążenie cieplne,
- właściwe normy systemowe / badawcze dla urządzeń wentylacyjnych i
  rekuperacyjnych.

Numer wydania normy, źródło danych klimatycznych i data obowiązywania podstawy
prawnej muszą być zapisane dla konkretnego obliczenia formalnego. Kod nie
traktuje komentarza w repozytorium jako dowodu aktualności normy lub prawa.

## Trzy poziomy użycia

### 1. Tryb legacy / diagnostyczny

Starsze projekty zachowują zgodność wsteczną. Jeżeli nie zostanie włączona
warstwa `metadata.normative`, kalkulator nadal może używać jawnie opisanych
uproszczeń diagnostycznych.

Taki wynik może służyć do analizy i porównań, ale ostrzeżenia audytowe wskazują
miejsca, których nie należy przedstawiać jako formalnie zweryfikowane.

### 2. Rozszerzony model godzinowy

Można włączyć osobno:

- model gruntu,
- szczegółową rekuperację,
- projektowe obciążenie cieplne.

W tym trybie użytkownik może korzystać z jawnych danych projektowych i
producenta, ale nadal może dopuścić współczynniki diagnostyczne. Każdy taki
przypadek pozostaje oznaczony jako ostrzeżenie.

### 3. Tryb formalny

`metadata.normative.legal.certificate_mode = true` powoduje, że brak wymaganych
danych wejściowych blokuje obliczenie zamiast tworzyć pozornie formalny wynik.

Wymagany jest m.in. ślad źródłowy:

- data obliczenia,
- podstawa metodologiczna / wersja aktu,
- źródło danych klimatycznych,
- pochodzenie współczynnika `wi` dla każdego używanego nośnika.

Dla budynku z kontaktem z gruntem wymagany jest również formalny tryb gruntu.
Dla wentylacji z odzyskiem wymagany jest szczegółowy model urządzenia i źródło
jego charakterystyki. Jeżeli obliczenie projektowego obciążenia jest włączone,
jego warunki projektowe również muszą być zweryfikowane.

## Struktura danych

Zaawansowane ustawienia są przechowywane w:

```json
{
  "metadata": {
    "normative": {
      "ground": {},
      "heat_recovery": {},
      "design_conditions": {},
      "legal": {}
    }
  }
}
```

Frontend zapisuje konfigurację w osobnym panelu i dołącza ją do żądania
`/api/calculate`. Dzięki temu starszy schemat projektu pozostaje kompatybilny.

---

# 1. Grunt — ISO 13370 + solver godzinowy

## Część stacjonarna

Dla podłogi na gruncie wyznaczana jest charakterystyczna wielkość:

```text
B' = 2 A / P
```

gdzie:

- `A` — powierzchnia podłogi [m²],
- `P` — obwód wystawiony na wymianę z gruntem [m].

Następnie wyznaczana jest zastępcza grubość cieplna i współczynnik przenikania
podłogi na gruncie z geometrii, przewodności gruntu oraz oporu cieplnego
warstw podłogi.

W trybie formalnym aplikacja wymaga jawnie:

- `soil_conductivity_w_mk`,
- `soil_density_kg_m3`,
- `soil_specific_heat_j_kgk`,
- `external_wall_thickness_m`,
- `floor_thermal_resistance_m2k_w`,
- obwodu eksponowanego lub jednoznacznych wymiarów rzutu.

Nie wolno zastępować oporu warstw podłogi przez `1/U` bez informacji o
konstrukcji. Taka operacja jest dostępna wyłącznie jako diagnostyczny fallback
i jest oznaczana ostrzeżeniem.

## Część okresowa

Standardowy sezonowy model ISO 13370 pracuje z okresem miesięcznym. Dla
integracji z 8760-godzinnym solverem dynamicznym potrzebna jest okresowa
odpowiedź odpowiednia do zastosowania dynamicznego.

Dlatego w trybie formalnym każda przegroda do gruntu wymaga jawnie pary:

- `periodic_amplitude_ratio`,
- `phase_shift_days`.

Współczynniki muszą pochodzić z właściwej, zweryfikowanej procedury dynamicznej
(np. z procedury wynikającej z właściwego zastosowania ISO 13370). Aplikacja
**nie wyprowadza ich z arbitralnej stałej**.

Jeżeli tryb formalny jest wyłączony, dostępny jest transparentny model
jednowymiarowej fali cieplnej w półnieskończonym gruncie. Wykorzystuje on:

```text
alpha = lambda / (rho * c)
```

oraz roczną głębokość penetracji cieplnej. Wynik jest zawsze oznaczany jako
**diagnostyczny**, a nie jako weryfikacja pełnej procedury dynamicznej normy.

## Integracja z 5R1C

Przygotowany profil temperatury granicznej i współczynnik `U` są przypisywane
do konkretnej przegrody przed budową sieci transmisyjnej 5R1C. Solver roczny
nie korzysta wtedy z dawnej, globalnej sinusoidy 5 K / 2 miesiące.

---

# 2. Rekuperacja godzinowa

## Zasada fizyczna

W szczegółowym modelu odzysku nie redukuje się sztucznie fizycznego strumienia
wentylacyjnego przez `1 - eta`.

Zachowany jest pełny strumień mechaniczny, a odzysk jest reprezentowany przez
godzinową temperaturę powietrza nawiewanego:

```text
T_supply = T_preheated + eta(t) * (T_extract - T_preheated)
```

Temperatura wyrzutowa wynosi odpowiednio:

```text
T_exhaust = T_extract - eta(t) * (T_extract - T_preheated)
```

Dzięki temu `Hve` odpowiada rzeczywistemu strumieniowi powietrza, a odzysk
wpływa na różnicę temperatur w bilansie.

## Charakterystyka sprawności

`eta(t)` może być interpolowana z punktów charakterystyki urządzenia w funkcji
temperatury zewnętrznej. Jeżeli krzywa nie została przekazana, model korzysta
z jawnej sprawności wpisanej w projekcie.

W trybie formalnym wymagane jest pole `performance_source`, wskazujące źródło
danych urządzenia (np. karta producenta / raport badania).

## Bypass letni

Bypass może zostać aktywowany tylko w zdefiniowanym przedziale temperatury
zewnętrznej i gdy powietrze zewnętrzne może realizować free-cooling względem
zadanej temperatury chłodzenia z wymaganym marginesem.

Jeżeli w projekcie nie ma temperatury docelowej chłodzenia/free-coolingu,
formalny model z aktywnym bypassem jest odrzucany.

## Ochrona przeciwzamrożeniowa

Obsługiwane strategie:

- brak aktywnej ochrony,
- nagrzewnica wstępna,
- ograniczenie sprawności odzysku,
- wyłączenie odzysku.

Ryzyko szronienia zależy od temperatury wyrzutowej. Jeżeli podano wilgotność
względną powietrza wywiewanego, dodatkowo sprawdzany jest punkt rosy.

W trybie formalnym aktywna strategia przeciwzamrożeniowa wymaga jawnego
`indoor_relative_humidity`. Kod nie wprowadza normatywnej emisji wilgoci od
użytkowników bez danych wejściowych.

## Nagrzewnica wstępna

Dla strategii `preheater` obliczana jest godzinowa moc elektryczna potrzebna do
utrzymania zadanej minimalnej temperatury wyrzutowej. Moc jest ograniczona
rzeczywistą mocą zainstalowanej nagrzewnicy.

Dla instalacji wielostrefowej moc jednego centralnego urządzenia jest dzielona
proporcjonalnie między strefy. Nie wolno mnożyć nominalnej mocy nagrzewnicy
przez liczbę stref.

Roczna energia nagrzewnicy jest dodawana do:

- `Ek`,
- `Ep` przez współczynnik energii elektrycznej,
- emisji CO2,
- mianownika udziału OZE.

Nie jest dodawana do `Eu`, ponieważ jest energią pomocniczą/systemową.

---

# 3. Projektowe obciążenie cieplne

Obliczenie projektowe jest całkowicie oddzielone od rocznego TMY.

## Warunki wejściowe

Wymagana jest jawna:

- projektowa temperatura zewnętrzna,
- informacja o źródle tej wartości w trybie formalnym,
- temperatura sąsiednia dla przestrzeni nieogrzewanych w formalnym wariancie,
- projektowa temperatura po stronie gruntu dla każdej przegrody gruntowej,
- ewentualna dodatkowa moc ponownego nagrzania `heat_up`.

W trybie formalnym temperatura gruntu **nie jest** zastępowana średnią z
rocznego profilu. Brak projektowej wartości dla konkretnej przegrody blokuje
obliczenie.

## Bilans

Dla strefy raportowane są osobno:

- strata przez przenikanie,
- strata przez wentylację,
- jawnie wprowadzona moc ponownego nagrzania,
- suma mocy projektowej.

Przegrody do zewnętrza korzystają z jawnej projektowej temperatury zewnętrznej.
Przegrody do gruntu i pomieszczeń nieogrzewanych korzystają z własnych
warunków projektowych.

Wentylacja korzysta z tej samej fizycznej charakterystyki odzysku ciepła, jeżeli
szczegółowy model rekuperatora został aktywowany.

## Czego nie robi obliczenie projektowe

Projektowe obciążenie cieplne:

- nie używa minimum z TMY,
- nie używa COP pompy ciepła ani sprawności kotła,
- nie jest energią roczną,
- nie jest automatycznie powiększane o CWU.

Jest to moc użyteczna potrzebna dla budynku/strefy w zadanych warunkach
projektowych. Dobór konkretnego źródła i strategii biwalencji jest osobnym
zagadnieniem systemowym.

---

# 4. Prawny ślad źródłowy w Polsce

Tryb formalny przechowuje dane pozwalające odtworzyć podstawę obliczenia.

Szczególną uwagę należy zwrócić na współczynnik nakładu nieodnawialnej energii
pierwotnej `wi`. Po zmianie metodologii obowiązującej od 28 kwietnia 2023 r.
dla nośnika lub energii należy w pierwszej kolejności wykorzystywać wartość
udostępnioną przez dostawcę; dopiero przy braku takich danych stosuje się
właściwą wartość tabelaryczną rozporządzenia.

Z tego powodu aplikacja nie traktuje domyślnego `wi=2,50` dla energii
elektrycznej jako wystarczającego dowodu formalnego. Tryb formalny wymaga pola
opisującego źródło `wi` dla każdego nośnika używanego przez budynek.

---

# 5. Granice odpowiedzialności implementacji

## Pełny tekst norm

Normy PKN/ISO są dokumentami chronionymi i pełna treść nie jest częścią
repozytorium. Kod nie powinien twierdzić, że niezależnie dowodzi zgodności
każdej klauzuli normy wyłącznie na podstawie publicznego opisu zakresu.

Dlatego tam, gdzie formalna procedura dynamiczna wymaga współczynników, których
nie można bezpiecznie wyprowadzić z publicznych danych, aplikacja wymaga ich
jawnego podania wraz ze źródłem zamiast zgadywać.

## Wilgotność

Model rekuperacji nie jest pełnym bilansem masowym wilgoci budynku. Do oceny
frost protection wykorzystuje jawną wilgotność względną powietrza wywiewanego.
Wprowadzenie pełnego godzinowego bilansu wilgoci wymagałoby źródeł emisji
wilgoci, sorpcji i ewentualnych systemów nawilżania/osuszania; bez tych danych
nie wolno tworzyć wartości normatywnych z założenia.

## Dane klimatyczne

Tryb formalny wymaga zapisania źródła zestawu klimatycznego. Sam plik TMYx lub
nazwa stacji nie stanowią automatycznie dowodu, że zestaw jest właściwy dla
konkretnego celu świadectwa i daty obliczenia.

---

# 6. Testy regresyjne

`backend/tests/test_normative_extensions.py` obejmuje m.in.:

- `B' = 2A/P`,
- monotoniczny spadek `U` gruntu przy wzroście oporu cieplnego podłogi,
- zachowanie średniej temperatury przez profil okresowy,
- blokadę niekompletnej pary współczynników okresowych,
- analityczny przypadek rekuperacji `eta = 0,8`, `0°C -> 16°C`,
- bypass letni,
- analityczny przypadek nagrzewnicy przeciwzamrożeniowej,
- brak mnożenia centralnej mocy nagrzewnicy przez liczbę stref,
- fizyczny pełny strumień `Hve` w szczegółowej rekuperacji,
- niezależność obciążenia projektowego od COP,
- wymóg jawnej temperatury gruntu w formalnym obciążeniu projektowym,
- blokadę legacy-ground w formalnym trybie prawnym,
- wymaganie źródła danych urządzenia i śladu prawnego.

Te testy są uzupełnieniem, a nie zastępstwem walidacji na oficjalnych
przykładach referencyjnych właściwych wydań norm.
