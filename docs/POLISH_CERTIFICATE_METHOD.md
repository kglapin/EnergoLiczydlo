# Formalna metoda charakterystyki energetycznej w Polsce

## 1. Cel dokumentu

Ten dokument opisuje sposób działania części aplikacji przeznaczonej do wyznaczania formalnej charakterystyki energetycznej budynku zgodnie z polską metodologią.

Najważniejsza zasada jest prosta:

**formalny wynik świadectwa i szczegółowa analiza godzinowa są dwoma różnymi wynikami.**

Aplikacja nie podstawia wyniku symulacji 8760 godzin w miejsce procedury wymaganej przez polską metodologię.

## 2. Dwa równoległe silniki obliczeniowe

### 2.1. Silnik formalnej charakterystyki energetycznej

W trybie świadectwa główne wskaźniki:

- energia użytkowa (`Eu`),
- energia końcowa (`Ek`),
- nieodnawialna energia pierwotna (`Ep`)

są wyznaczane przez miesięczny silnik formalny.

Silnik korzysta z danych i współczynników wymaganych przez polską metodologię charakterystyki energetycznej.

### 2.2. Godzinowa analiza fizyczna

Równolegle aplikacja może wykonać analizę 8760 godzin roku z wykorzystaniem modelu opartego na PN-EN ISO 52016-1.

Ta analiza pokazuje m.in.:

- godzinowe temperatury wewnętrzne,
- godzinowe zapotrzebowanie na ogrzewanie i chłodzenie,
- działanie zysków słonecznych i wewnętrznych,
- pracę wentylacji z odzyskiem ciepła,
- wpływ wymiany ciepła z gruntem.

Wynik godzinowy służy do diagnostyki, porównywania wariantów i kontroli jakości. Nie jest automatycznie formalnym wynikiem świadectwa.

## 3. Kiedy aplikacja używa formalnego silnika

Formalny tryb jest aktywny, gdy w projekcie ustawiono:

```text
metadata.normative.legal.certificate_mode = true
```

Po jego włączeniu główne wartości `Eu`, `Ek`, `Ep` oraz miesięczne zestawienia formalne pochodzą z miesięcznego silnika świadectwa.

Godzinowy wynik 8760 godzin pozostaje zapisany jako analiza równoległa.

## 4. Miesięczny bilans ogrzewania

Dla każdego miesiąca formalny silnik oblicza zapotrzebowanie na energię użytkową do ogrzewania.

W uproszczonym zapisie:

```text
zapotrzebowanie na ogrzewanie
=
straty ciepła
-
wykorzystana część zysków ciepła
```

W kodzie odpowiada temu zapis:

```text
QH,nd,n = QH,ht,n - ηH,gn,n × QH,gn,n
```

Znaczenie symboli:

- `QH,nd,n` – zapotrzebowanie na energię użytkową do ogrzewania w danym miesiącu,
- `QH,ht,n` – miesięczne straty ciepła przez przenikanie i wentylację,
- `QH,gn,n` – miesięczne zyski ciepła,
- `ηH,gn,n` – miesięczny współczynnik wykorzystania zysków ciepła.

Wynik nie może być ujemny.

## 5. Miesięczny bilans chłodzenia

Dla chłodzenia stosowana jest analogiczna logika.

W uproszczeniu:

```text
zapotrzebowanie na chłodzenie
=
zyski ciepła
-
część strat ciepła, którą można wykorzystać do ograniczenia chłodzenia
```

W kodzie:

```text
QC,nd,n = QC,gn,n - ηC,ls,n × QC,ht,n
```

Znaczenie symboli:

- `QC,nd,n` – zapotrzebowanie na energię użytkową do chłodzenia w danym miesiącu,
- `QC,gn,n` – miesięczne zyski ciepła,
- `QC,ht,n` – miesięczne straty ciepła,
- `ηC,ls,n` – miesięczny współczynnik wykorzystania strat ciepła.

Wynik również nie może być ujemny.

## 6. Dane wymagane dla każdego miesiąca

Formalny silnik może wymagać 12 wartości, po jednej dla każdego miesiąca roku, między innymi dla:

- temperatury zewnętrznej,
- temperatury wewnętrznej przy ogrzewaniu,
- temperatury wewnętrznej przy chłodzeniu,
- współczynnika wykorzystania zysków ciepła,
- współczynnika wykorzystania strat ciepła,
- udziału czasu użytkowania,
- skuteczności odzysku ciepła,
- temperatury gruntu,
- temperatury pomieszczeń nieogrzewanych,
- energii zużywanej przez nagrzewnicę wstępną, jeżeli występuje.

Każda seria miesięczna musi zawierać dokładnie 12 wartości.

## 7. Zyski słoneczne

Dla każdej przegrody przezroczystej, np. okna albo świetlika, formalny silnik może wymagać miesięcznych danych dotyczących promieniowania słonecznego docierającego do tej przegrody.

Dane te są oddzielone od promieniowania używanego w analizie godzinowej.

Oznacza to, że aplikacja nie zakłada automatycznie, że plik klimatyczny używany do symulacji 8760 godzin jest właściwym źródłem danych dla formalnego świadectwa.

## 8. Dane klimatyczne

W trybie świadectwa użytkownik musi wskazać źródło danych klimatycznych użytych do formalnego obliczenia.

Pole:

```text
official_bip_climate_data
```

służy do potwierdzenia, że wykorzystano odpowiedni oficjalny zestaw danych klimatycznych.

Samo zaznaczenie pola nie zastępuje obowiązku wskazania konkretnego źródła w śladzie dokumentacyjnym projektu.

## 9. Współczynniki wyznaczane zgodnie z Polską Normą

Jeżeli polska metodologia wskazuje, że określony współczynnik należy wyznaczyć zgodnie z Polską Normą, aplikacja nie powinna odtwarzać go na podstawie niezweryfikowanego wzoru.

Dotyczy to między innymi miesięcznych współczynników wykorzystania zysków i strat.

Dlatego w trybie świadectwa użytkownik podaje zweryfikowane wartości oraz wskazuje ich źródło.

Jest to celowe zabezpieczenie przed tworzeniem pozornie dokładnego wyniku na podstawie nieudokumentowanych założeń.

## 10. Wentylacja i odzysk ciepła

Formalny silnik miesięczny rozdziela m.in.:

- podstawowy strumień powietrza,
- udział czasu działania wentylacji,
- infiltrację,
- pracę instalacji poza okresem użytkowania,
- skuteczność odzysku ciepła,
- dodatkowe współczynniki redukcyjne wymagane przez metodologię.

Szczegółowa godzinowa symulacja rekuperatora nie jest automatycznie uśredniana i przenoszona do formalnego świadectwa.

Jeżeli formalne obliczenie wymaga miesięcznej skuteczności odzysku ciepła, należy podać odpowiednią serię 12 wartości.

## 11. Nagrzewnica wstępna i ochrona przed zamarzaniem

W analizie godzinowej aplikacja może obliczać energię zużywaną przez nagrzewnicę wstępną chroniącą wymiennik przed zamarzaniem.

Formalny silnik świadectwa nie pobiera tej wartości automatycznie z typowego roku meteorologicznego.

Jeżeli energia nagrzewnicy ma wpływać na formalny wynik, należy podać miesięczną serię:

```text
preheater_electricity_kwh_by_month
```

czyli 12 miesięcznych wartości zużycia energii elektrycznej.

## 12. Ciepła woda użytkowa

Zapotrzebowanie na energię użytkową do przygotowania ciepłej wody użytkowej jest wyznaczane osobno od ogrzewania i chłodzenia.

Następnie energia użytkowa jest przeliczana na energię końcową z uwzględnieniem parametrów systemu przygotowania ciepłej wody.

## 13. Energia użytkowa, końcowa i pierwotna

### Energia użytkowa (`Eu`)

Opisuje potrzeby energetyczne budynku przed uwzględnieniem strat i sprawności systemów technicznych.

### Energia końcowa (`Ek`)

Opisuje energię, którą trzeba dostarczyć do systemów technicznych po uwzględnieniu ich sprawności, strat i energii pomocniczej.

### Nieodnawialna energia pierwotna (`Ep`)

Powstaje przez przeliczenie energii końcowej za pomocą odpowiednich współczynników nakładu nieodnawialnej energii pierwotnej dla zastosowanych nośników energii.

Nie należy zakładać uniwersalnej relacji `Ep ≥ Ek ≥ Eu`. Na przykład pompa ciepła może mieć energię końcową niższą od energii użytkowej, ponieważ wykorzystuje również energię pobieraną ze środowiska.

## 14. Współczynnik nakładu nieodnawialnej energii pierwotnej

Dla każdego nośnika energii formalny tryb zapisuje:

- zastosowaną wartość współczynnika,
- źródło tej wartości.

Jeżeli dla konkretnego przypadku należy wykorzystać wartość udostępnioną przez dostawcę energii, użytkownik może nadpisać wartość domyślną w projekcie.

Jeżeli stosowana jest wartość z tabeli metodologii, powinno to być jasno opisane jako źródło zastosowanego współczynnika.

## 15. Projektowe obciążenie cieplne

Projektowe obciążenie cieplne jest osobnym wynikiem i nie jest częścią rocznego bilansu energii.

Nie wpływa bezpośrednio na `Eu`, `Ek` ani `Ep`.

Służy do określenia wymaganej mocy cieplnej budynku lub strefy w zadanych warunkach projektowych.

## 16. Blokada obliczenia przy braku wymaganych danych

W trybie świadectwa brak danych wymaganych do formalnego obliczenia nie uruchamia cichej wartości zastępczej.

Obliczenie jest blokowane, jeżeli brakuje np.:

- formalnych danych klimatycznych,
- miesięcznych współczynników wymaganych przez metodologię,
- danych dotyczących gruntu, jeżeli są potrzebne,
- dokumentacji odzysku ciepła, jeżeli wpływa na wynik,
- źródła współczynnika nakładu nieodnawialnej energii pierwotnej.

Zasada jest celowa: **lepiej zatrzymać formalne obliczenie niż wygenerować wynik oparty na nieudokumentowanym założeniu.**

## 17. Powiązane dokumenty

- `NORMATIVE_HOURLY_V2.md` – szczegółowa analiza godzinowa i moduły techniczne,
- `METHODOLOGY.md` – ogólna metodologia projektu,
- `COMPUTATION_LOGIC.md` – techniczny przebieg obliczeń,
- `INPUT_SCHEMA.md` – struktura danych wejściowych,
- `VALIDATION.md` – zasady testowania i walidacji.
