# Logika obliczeniowa aplikacji

## 1. Cel dokumentu

Ten dokument opisuje techniczny przebieg obliczeń w aktualnej wersji Energoliczydła.

Aplikacja nie ma jednego wyniku obliczeniowego. Rozdziela trzy ścieżki:

1. **formalną charakterystykę energetyczną w Polsce**,
2. **godzinową analizę fizyczną budynku**,
3. **projektowe obciążenie cieplne**.

Każda z tych ścieżek ma inne przeznaczenie i inne wymagania dotyczące danych wejściowych.

## 2. Formalna charakterystyka energetyczna

W trybie świadectwa główne wskaźniki:

- energia użytkowa (`Eu`),
- energia końcowa (`Ek`),
- nieodnawialna energia pierwotna (`Ep`)

pochodzą z miesięcznego silnika formalnego.

Silnik formalny korzysta z danych miesięcznych i współczynników wymaganych przez polską metodologię charakterystyki energetycznej.

Wynik godzinowy nie jest podstawiany w miejsce formalnego wyniku miesięcznego.

## 3. Godzinowa analiza fizyczna

Godzinowy silnik analizuje 8760 godzin roku nieprzestępnego.

Główna kolejność obliczeń jest następująca:

1. wczytanie danych klimatycznych,
2. sprawdzenie kompletności 8760 godzin,
3. wyznaczenie położenia słońca i promieniowania na przegrody,
4. przygotowanie geometrii netto przegród,
5. przygotowanie warunków brzegowych, w tym gruntu i przestrzeni sąsiednich,
6. przygotowanie wentylacji, infiltracji i odzysku ciepła,
7. wyznaczenie zysków wewnętrznych i słonecznych,
8. rozwiązanie godzinowego bilansu cieplnego dla każdej strefy,
9. wyznaczenie godzinowego zapotrzebowania na ogrzewanie i chłodzenie,
10. przeliczenie energii użytkowej na energię końcową dla analizy godzinowej,
11. agregacja godzin do miesięcy i roku,
12. zapis wyniku jako analizy technicznej.

Jeżeli aktywny jest tryb świadectwa, ten wynik pozostaje dostępny jako analiza równoległa.

## 4. Kontrola danych przed obliczeniem

Przed uruchomieniem głównego silnika wykonywana jest kontrola danych projektu.

Kontrola obejmuje między innymi:

- zgodność powierzchni stref z powierzchnią o regulowanej temperaturze,
- zgodność kubatur stref z kubaturą ogrzewaną,
- poprawność identyfikatorów stref,
- poprawność przypisania przegród do stref,
- poprawność zakresów współczynników,
- kompletność wymaganych danych systemów technicznych,
- poprawność geometrii ścian i otworów,
- kompletność danych formalnych w trybie świadectwa.

Problemy są dzielone na:

- błędy blokujące obliczenie,
- ostrzeżenia wymagające świadomej kontroli użytkownika.

## 5. Powierzchnie ścian i otworów

Przegroda przezroczysta, np. okno, musi być przypisana do właściwej przegrody nadrzędnej.

Powierzchnia nieprzezroczysta ściany jest liczona jako:

```text
powierzchnia netto ściany
=
powierzchnia brutto ściany
-
suma powierzchni przypisanych otworów
```

Jeżeli okna mają łącznie większą powierzchnię niż ściana, obliczenie jest blokowane.

Jeżeli otwór pasuje do kilku przegród i nie można jednoznacznie określić przegrody nadrzędnej, użytkownik musi wskazać ją jawnie.

## 6. Przenikanie przez przegrody

Dla przegrody nieprzezroczystej albo przezroczystej podstawowa przewodność cieplna wynika z:

```text
H = U × A
```

gdzie:

- `H` – przewodność cieplna w watach na kelwin,
- `U` – współczynnik przenikania ciepła w watach na metr kwadratowy i kelwin,
- `A` – powierzchnia w metrach kwadratowych.

Mostki cieplne są dodawane osobno.

Dla liniowego mostka cieplnego:

```text
H_mostka = ψ × L
```

gdzie:

- `ψ` – liniowy współczynnik przenikania ciepła,
- `L` – długość mostka.

Dla punktowego mostka cieplnego wykorzystywany jest współczynnik punktowy i liczba wystąpień.

## 7. Model godzinowy 5R1C

Godzinowy bilans cieplny korzysta z uproszczonej sieci cieplnej 5R1C.

Model rozróżnia między innymi:

- temperaturę powietrza wewnętrznego,
- temperaturę powierzchni wewnętrznych,
- temperaturę masy cieplnej budynku,
- wymianę przez przegrody nieprzezroczyste,
- wymianę przez okna,
- wymianę przez wentylację.

Zyski wewnętrzne i słoneczne są rozdzielane pomiędzy odpowiednie węzły modelu.

Dla każdej godziny najpierw wyznaczana jest temperatura swobodna, czyli temperatura bez aktywnego ogrzewania lub chłodzenia. Następnie, jeżeli temperatura przekracza zadane granice, wyznaczana jest moc potrzebna do utrzymania zadanej temperatury.

## 8. Warunki brzegowe przegród

Przegroda może graniczyć z:

- powietrzem zewnętrznym,
- gruntem,
- przestrzenią nieogrzewaną,
- przestrzenią o zadanej stałej temperaturze,
- inną strefą kondycjonowaną.

Każdy typ granicy ma osobną logikę wyznaczania temperatury po drugiej stronie przegrody.

## 9. Grunt

Dla rozszerzonego modelu gruntu wykorzystywany jest moduł oparty na danych wymaganych do opisu wymiany ciepła z gruntem.

Dane mogą obejmować:

- powierzchnię podłogi,
- obwód wystawiony na wymianę z gruntem,
- opór cieplny podłogi,
- właściwości cieplne gruntu,
- parametry zmienności okresowej.

Stary, globalny model sinusoidalny może występować wyłącznie jako rozwiązanie diagnostyczne dla starszych projektów. Nie jest traktowany jako formalnie zweryfikowany model gruntu.

## 10. Wentylacja i infiltracja

Podstawowa przewodność cieplna wentylacji jest wyznaczana z fizycznego strumienia powietrza.

W uproszczonym zapisie:

```text
Hve = ρ × cp × qv
```

gdzie:

- `Hve` – przewodność cieplna wentylacji,
- `ρ × cp` – objętościowa pojemność cieplna powietrza,
- `qv` – strumień objętościowy powietrza.

W silniku używana jest wartość objętościowej pojemności cieplnej powietrza `1200 J/(m³·K)`.

Do strumienia wentylacyjnego może zostać dodana infiltracja zależna od kubatury strefy.

## 11. Odzysk ciepła

W szczegółowym modelu odzysku ciepła pełny strumień powietrza pozostaje w obliczeniu.

Odzysk ciepła zmienia temperaturę nawiewu.

Model może uwzględniać:

- sprawność zależną od temperatury,
- obejście letnie wymiennika,
- ochronę przed zamarzaniem,
- nagrzewnicę wstępną,
- ograniczenie mocą urządzenia.

Energia nagrzewnicy wstępnej jest dodawana do energii systemowej i nie zwiększa energii użytkowej.

## 12. Zyski słoneczne

Dla okna godzinowy zysk słoneczny zależy między innymi od:

```text
powierzchnia przeszklenia
× udział części przezroczystej
× współczynnik przepuszczania energii słonecznej
× współczynnik zacienienia
× promieniowanie na powierzchnię
```

Orientacja i nachylenie przegrody wpływają na promieniowanie padające na daną powierzchnię.

## 13. Zyski wewnętrzne

Zyski wewnętrzne mogą pochodzić od:

- ludzi,
- oświetlenia,
- urządzeń.

Jeżeli użytkownik poda szczegółowe harmonogramy, zyski zmieniają się godzinowo. Jeżeli nie poda harmonogramów, stosowany jest jawnie określony profil lub wartość uśredniona właściwa dla danego trybu obliczeń.

## 14. Ogrzewanie i chłodzenie w analizie godzinowej

Dla każdej godziny silnik wyznacza oddzielnie:

- energię potrzebną do ogrzewania,
- energię potrzebną do chłodzenia.

Ogrzewanie i chłodzenie nie mogą być jednocześnie dodatnie dla tej samej strefy w tej samej godzinie.

## 15. System ogrzewania

Energia końcowa ogrzewania zależy od energii użytkowej i łącznej sprawności systemu.

Dla pompy ciepła współczynnik efektywności może być większy od 1. Z tego powodu energia końcowa może być mniejsza od energii użytkowej.

Nie należy stosować uniwersalnego założenia, że energia końcowa musi być większa od energii użytkowej.

## 16. System chłodzenia

Chłodzenie jest rozliczane analogicznie do ogrzewania, z uwzględnieniem parametrów systemu chłodniczego.

Jeżeli strefa nie ma aktywnego chłodzenia, sam fakt podania temperatury zadanej chłodzenia nie oznacza automatycznie aktywnego systemu chłodniczego.

## 17. Ciepła woda użytkowa

Zapotrzebowanie użytkowe na ciepłą wodę jest wyznaczane na podstawie powierzchni i profilu użytkowania właściwego dla budynku.

Następnie jest przeliczane na energię końcową z uwzględnieniem:

- sprawności źródła,
- strat magazynowania,
- strat dystrybucji,
- sprawności wykorzystania.

Jeżeli system z zasobnikiem nie ma danych potrzebnych do oceny strat postojowych, aplikacja zgłasza ostrzeżenie albo blokuje formalne obliczenie, zależnie od trybu.

## 18. Energia pomocnicza

Energia pomocnicza może obejmować między innymi:

- pompy obiegowe,
- wentylatory,
- automatykę,
- nagrzewnicę wstępną.

Energia pomocnicza wpływa na energię końcową i nieodnawialną energię pierwotną, ale nie zwiększa energii użytkowej.

## 19. Energia pierwotna

Energia końcowa jest grupowana według nośników energii.

Dla każdego nośnika energia końcowa jest mnożona przez właściwy współczynnik nakładu nieodnawialnej energii pierwotnej.

W trybie świadectwa zapisywane jest również źródło zastosowanego współczynnika.

## 20. Udział odnawialnych nośników energii

Przy obliczaniu udziału odnawialnych nośników aplikacja uwzględnia właściwe kategorie nośników, w tym między innymi:

- biomasę,
- biogaz,
- energię słoneczną,
- energię wiatru,
- energię geotermalną.

## 21. Formalny silnik miesięczny

Jeżeli aktywny jest tryb świadectwa, po wykonaniu analizy godzinowej uruchamiany jest formalny silnik miesięczny.

Formalny silnik wyznacza miesięczne potrzeby ogrzewania i chłodzenia na podstawie danych wymaganych przez polską metodologię.

Następnie oblicza:

- roczną energię użytkową,
- energię końcową według nośników,
- nieodnawialną energię pierwotną,
- emisję dwutlenku węgla,
- udział odnawialnych źródeł energii.

W trybie świadectwa to właśnie te wartości stają się głównym formalnym wynikiem aplikacji.

## 22. Zachowanie wyniku godzinowego

Po uruchomieniu formalnego silnika godzinowa analiza nie jest usuwana.

Pozostaje dostępna w diagnostyce, aby można było porównać:

- formalny wynik miesięczny,
- godzinową odpowiedź fizyczną budynku.

Różnica między tymi wynikami nie musi oznaczać błędu, ponieważ wynikają z różnych procedur i innego sposobu agregowania danych.

## 23. Projektowe obciążenie cieplne

Projektowe obciążenie cieplne jest liczone osobno od energii rocznej.

Wykorzystuje:

- projektową temperaturę zewnętrzną,
- projektowe temperatury po stronie gruntu,
- temperatury przestrzeni nieogrzewanych,
- straty przez przenikanie,
- straty wentylacyjne,
- opcjonalną moc ponownego nagrzania.

Nie wykorzystuje najzimniejszej godziny typowego roku meteorologicznego jako substytutu temperatury projektowej.

Nie zależy od sprawności generatora ani współczynnika COP źródła.

## 24. Kontrole końcowe

Po obliczeniu sprawdzane są między innymi:

- skończoność wartości liczbowych,
- nieujemność energii użytkowych,
- zgodność sum godzinowych, miesięcznych i rocznych tam, gdzie dotyczą tej samej ścieżki obliczeniowej,
- brak jednoczesnego ogrzewania i chłodzenia,
- spójność danych formalnych,
- zachowanie analizy godzinowej po uruchomieniu trybu świadectwa.

## 25. Ważne ograniczenie

Przejście wszystkich testów oprogramowania nie oznacza automatycznie, że każda wartość wejściowa konkretnego świadectwa jest prawidłowa.

Odpowiedzialność za dane projektowe, źródła współczynników i właściwy zestaw danych klimatycznych pozostaje częścią procesu przygotowania obliczenia.
