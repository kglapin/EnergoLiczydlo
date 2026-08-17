# Rozszerzony model godzinowy i obliczenia projektowe

## 1. Cel dokumentu

Ten dokument opisuje szczegółową analizę fizyczną budynku wykonywaną z krokiem jednej godziny oraz dodatkowe moduły techniczne wykorzystywane przez tę analizę.

Model godzinowy obejmuje 8760 godzin typowego roku meteorologicznego i służy przede wszystkim do:

- analizy temperatur wewnętrznych,
- analizy zapotrzebowania na ogrzewanie i chłodzenie w kolejnych godzinach,
- oceny wpływu zysków słonecznych i wewnętrznych,
- analizy pracy wentylacji i odzysku ciepła,
- analizy wymiany ciepła z gruntem,
- kontroli jakości danych wejściowych,
- porównania z formalnym wynikiem charakterystyki energetycznej.

**Model godzinowy nie zastępuje formalnej procedury świadectwa charakterystyki energetycznej obowiązującej w Polsce.**

Jeżeli w projekcie włączono tryb świadectwa, główne wskaźniki formalne:

- energia użytkowa (`Eu`),
- energia końcowa (`Ek`),
- nieodnawialna energia pierwotna (`Ep`)

pochodzą z osobnego silnika miesięcznego opisanego w `POLISH_CERTIFICATE_METHOD.md`.

Wynik godzinowy jest wtedy zachowywany jako równoległa analiza techniczna.

## 2. Trzy rodzaje wyników w aplikacji

Aplikacja rozróżnia trzy niezależne wyniki.

### 2.1. Formalna charakterystyka energetyczna

Jest to wynik przeznaczony do obliczeń wykonywanych zgodnie z polską metodologią świadectw charakterystyki energetycznej.

W trybie świadectwa aplikacja korzysta z miesięcznych danych i współczynników wymaganych przez metodologię. Brak danych wymaganych do formalnego obliczenia blokuje wynik.

### 2.2. Godzinowa analiza fizyczna

Jest to szczegółowa symulacja 8760 godzin roku, oparta na modelu zgodnym z przeznaczeniem PN-EN ISO 52016-1.

Wynik godzinowy może służyć do:

- diagnostyki projektu,
- oceny dynamiki budynku,
- analizy komfortu i pracy instalacji,
- porównań wariantów,
- kontroli spójności wyniku formalnego.

### 2.3. Projektowe obciążenie cieplne

Jest to osobne obliczenie mocy cieplnej wymaganej w projektowych warunkach zewnętrznych.

Projektowe obciążenie cieplne:

- nie jest energią roczną,
- nie jest dodawane do `Eu`, `Ek` ani `Ep`,
- nie zależy od współczynnika COP pompy ciepła ani sprawności kotła,
- nie jest wyznaczane z najzimniejszej godziny typowego roku meteorologicznego.

## 3. Poziomy użycia modelu godzinowego

### 3.1. Tryb diagnostyczny

Starsze projekty mogą działać bez wszystkich zaawansowanych danych. Jeżeli brakuje informacji, silnik może korzystać z jawnie opisanych uproszczeń diagnostycznych.

Takiego wyniku nie należy przedstawiać jako formalnie zweryfikowanego.

### 3.2. Rozszerzona analiza godzinowa

Można włączyć dodatkowo:

- szczegółowy model wymiany ciepła z gruntem,
- szczegółowy model odzysku ciepła w wentylacji,
- projektowe obciążenie cieplne.

W tym trybie użytkownik może podawać dane projektowe i dane producenta urządzeń.

### 3.3. Tryb świadectwa

Włączenie pola:

```text
metadata.normative.legal.certificate_mode = true
```

powoduje, że aplikacja nie może zastępować brakujących danych formalnych nieudokumentowaną wartością domyślną.

W szczególności wymagane jest zapisanie źródła:

- danych klimatycznych,
- współczynników wymaganych przez metodologię,
- wartości współczynników nakładu nieodnawialnej energii pierwotnej,
- danych urządzeń, jeżeli wpływają na wynik formalny.

## 4. Wymiana ciepła z gruntem

### 4.1. Dane geometryczne

Dla przegrody stykającej się z gruntem wykorzystywana jest między innymi charakterystyczna wielkość:

```text
B' = 2 × A / P
```

gdzie:

- `A` oznacza powierzchnię podłogi stykającej się z gruntem w metrach kwadratowych,
- `P` oznacza obwód tej podłogi wystawiony na wymianę ciepła z gruntem w metrach.

Model korzysta również z danych takich jak:

- przewodność cieplna gruntu,
- gęstość gruntu,
- ciepło właściwe gruntu,
- opór cieplny warstw podłogi,
- grubość ściany zewnętrznej,
- parametry okresowej odpowiedzi cieplnej.

### 4.2. Dane wymagane w rozszerzonym modelu

Dla formalnie kontrolowanego modelu gruntu aplikacja wymaga jawnego podania między innymi:

- `soil_conductivity_w_mk` – przewodności cieplnej gruntu,
- `soil_density_kg_m3` – gęstości gruntu,
- `soil_specific_heat_j_kgk` – ciepła właściwego gruntu,
- `external_wall_thickness_m` – grubości ściany zewnętrznej,
- `floor_thermal_resistance_m2k_w` – oporu cieplnego warstw podłogi,
- `exposed_perimeter_m` – obwodu podłogi wystawionego na wymianę z gruntem.

Nazwy pól pozostają angielskie, ponieważ są częścią struktury danych programu, ale ich znaczenie musi być zawsze opisane po polsku.

### 4.3. Zmienność w czasie

W analizie godzinowej grunt jest warunkiem brzegowym zmieniającym się w czasie.

W trybie wymagającym pełnej kontroli danych okresowych aplikacja oczekuje dwóch jawnych parametrów dla danej przegrody:

- `periodic_amplitude_ratio` – współczynnika określającego, jak silnie roczna zmiana temperatury zewnętrznej jest tłumiona w gruncie,
- `phase_shift_days` – przesunięcia w dniach między zmianą temperatury zewnętrznej a odpowiedzią cieplną gruntu.

Jeżeli te parametry nie pochodzą ze zweryfikowanej procedury, wynik jest oznaczany jako diagnostyczny.

Dawna globalna sinusoida o stałej amplitudzie 5 K i stałym przesunięciu około dwóch miesięcy nie jest traktowana jako formalny model gruntu.

## 5. Wentylacja z odzyskiem ciepła

### 5.1. Zasada obliczenia

W szczegółowym modelu wentylacji nie zmniejsza się sztucznie fizycznego strumienia powietrza tylko po to, aby uwzględnić odzysk ciepła.

Pełny strumień wentylacyjny pozostaje w obliczeniu, natomiast odzysk ciepła wpływa na temperaturę powietrza nawiewanego.

W uproszczonym zapisie:

```text
T_nawiewu = T_przed_wymiennikiem + sprawność × (T_wywiewu - T_przed_wymiennikiem)
```

Temperatura powietrza usuwanego po wymienniku jest wyznaczana analogicznie.

### 5.2. Charakterystyka sprawności urządzenia

Sprawność odzysku może zmieniać się wraz z temperaturą zewnętrzną. Jeżeli użytkownik poda charakterystykę urządzenia, aplikacja interpoluje sprawność pomiędzy punktami tej charakterystyki.

W trybie wymagającym udokumentowania urządzenia pole `performance_source` musi wskazywać źródło danych, np. kartę producenta albo raport z badania.

### 5.3. Obejście letnie wymiennika

Obejście letnie, czyli bypass, może zostać uruchomione wtedy, gdy warunki zewnętrzne pozwalają wykorzystać chłodniejsze powietrze zewnętrzne bez odzyskiwania ciepła z powietrza usuwanego.

Aplikacja wymaga określenia zakresu temperatur pracy obejścia oraz warunku związanego z temperaturą wewnętrzną.

### 5.4. Ochrona przed zamarzaniem

Model obsługuje następujące strategie:

- brak aktywnej ochrony,
- nagrzewnicę wstępną,
- ograniczenie odzysku ciepła,
- czasowe wyłączenie odzysku ciepła.

Ryzyko zamarzania zależy od temperatur po obu stronach wymiennika. Jeżeli podano wilgotność względną powietrza usuwanego, model uwzględnia również temperaturę punktu rosy.

### 5.5. Nagrzewnica wstępna

Jeżeli aktywna jest nagrzewnica wstępna, aplikacja oblicza jej godzinową moc potrzebną do utrzymania wymaganych warunków pracy wymiennika.

Energia zużyta przez nagrzewnicę:

- zwiększa energię końcową,
- wpływa na nieodnawialną energię pierwotną przez właściwy współczynnik nośnika,
- wpływa na emisję dwutlenku węgla,
- nie zwiększa energii użytkowej budynku, ponieważ jest energią zużywaną przez system techniczny.

W budynku wielostrefowym moc jednego centralnego urządzenia nie jest mnożona przez liczbę stref.

## 6. Projektowe obciążenie cieplne

Projektowe obciążenie cieplne jest liczone niezależnie od typowego roku meteorologicznego.

Wymagane są między innymi:

- projektowa temperatura zewnętrzna,
- źródło tej temperatury, jeżeli wynik ma być formalnie udokumentowany,
- projektowa temperatura po stronie gruntu dla przegród stykających się z gruntem,
- temperatura przestrzeni nieogrzewanej po drugiej stronie przegrody,
- opcjonalna dodatkowa moc potrzebna do ponownego nagrzania pomieszczenia.

Raport pokazuje osobno:

- straty przez przenikanie,
- straty wentylacyjne,
- dodatkową moc ponownego nagrzania,
- łączną moc projektową strefy i budynku.

## 7. Współczynnik nakładu nieodnawialnej energii pierwotnej

Współczynnik określający nakład nieodnawialnej energii pierwotnej jest w kodzie przechowywany jako `wi` albo `fp`, zależnie od warstwy programu.

W dokumentacji i interfejsie należy zawsze wyjaśnić, że jest to współczynnik służący do przeliczenia energii końcowej na nieodnawialną energię pierwotną.

W trybie świadectwa sama wartość liczbowa nie wystarcza. Aplikacja zapisuje również źródło zastosowanej wartości.

## 8. Granice modelu

### 8.1. Pełne teksty norm

Repozytorium nie zawiera pełnych, chronionych tekstów norm. Jeżeli procedura wymaga współczynnika, którego nie można bezpiecznie odtworzyć na podstawie dostępnych i zweryfikowanych danych, aplikacja wymaga jego jawnego podania wraz ze źródłem.

### 8.2. Wilgotność

Model odzysku ciepła nie jest pełnym bilansem masowym wilgoci całego budynku. Wilgotność względna powietrza usuwanego jest wykorzystywana do oceny warunków pracy wymiennika, jeżeli została jawnie podana.

### 8.3. Dane klimatyczne

Typowy rok meteorologiczny wykorzystywany przez analizę godzinową i dane klimatyczne wykorzystywane przez formalny silnik świadectwa są traktowane jako dwa oddzielne źródła danych.

Nie wolno automatycznie zakładać, że dane używane do analizy godzinowej są jednocześnie właściwymi danymi dla formalnego świadectwa.

## 9. Powiązane dokumenty

- `POLISH_CERTIFICATE_METHOD.md` – formalna metoda świadectwa w Polsce,
- `METHODOLOGY.md` – ogólny opis metodologii,
- `COMPUTATION_LOGIC.md` – techniczny przebieg obliczeń,
- `INPUT_SCHEMA.md` – struktura danych wejściowych,
- `VALIDATION.md` – zasady testowania i walidacji.
