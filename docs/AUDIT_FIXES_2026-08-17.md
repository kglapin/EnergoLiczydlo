# Audyt obliczeń — poprawki 2026-08-17

Ten dokument opisuje zmiany wprowadzone po audycie kompletności i spójności obliczeń charakterystyki energetycznej.

## Zaimplementowane zabezpieczenia

### Powierzchnie brutto/netto

Przegrody transparentne są przed obliczeniem przypisywane do jednoznacznej przegrody zewnętrznej w tej samej strefie, o tej samej orientacji i nachyleniu. Powierzchnia okien/drzwi/skylightów jest odejmowana od powierzchni brutto przegrody nieprzezroczystej. Dzięki temu dodanie 1 m² okna zmienia Htr o `Uw - Uwall`, a nie o samo `Uw`.

Model jest odrzucany, jeżeli:

- powierzchnia otworów przekracza powierzchnię brutto hosta,
- otwór nie ma odpowiadającej mu przegrody zewnętrznej,
- otwór pasuje do więcej niż jednej przegrody i przypisanie jest niejednoznaczne.

W modelach z kilkoma segmentami ścian o tej samej orientacji można podać jawne przypisanie w `metadata.opening_hosts`, np. `{ "window_1": "wall_segment_2" }`. Walidacja nadal sprawdza zgodność strefy, typu granicy, orientacji i nachylenia, więc samo wskazanie identyfikatora nie omija kontroli fizycznej spójności.

### Kontrola kompletności geometrii

Audyt preflight generuje ostrzeżenia dla:

- braku dachu/górnej granicy lub podłogi/dolnej granicy,
- dużej rozbieżności między `Af / liczba kondygnacji` a powierzchnią dachu/podłogi,
- podejrzanie małej liczby kierunków ścian zewnętrznych,
- dużej rozbieżności między wysokością wynikającą z `V/Af` a podanymi wysokościami ścian.

Są to ostrzeżenia, nie twarde błędy, ponieważ nieregularna geometria i wielostrefowość mogą być fizycznie poprawne.

### Założenia instalacyjne

Raport audytowy wskazuje, gdy:

- nie podano rodzaju instalacji ogrzewania i nie podano jawnej energii pomocniczej — energia pomp obiegowych może być wtedy pominięta,
- system CWU z zasobnikiem nie ma geometrii zasobnika i `ηW,s = 1`, co oznacza zerowe straty postojowe,
- nie wprowadzono żadnych mostków cieplnych (`H_bridge = 0 W/K`).

### Udział OZE

`Uoze` uwzględnia wszystkie obsługiwane odnawialne nośniki energii końcowej:

- biomass,
- biogas,
- solar,
- wind,
- geothermal,
- legacy `renewable`.

### Raport założeń

Wyniki zawierają osobne informacje/ostrzeżenia audytowe dotyczące m.in.:

- wartości wejściowych wentylacji i infiltracji,
- współczynnika energii pierwotnej,
- pochodzenia danych `wi` w trybie formalnym,
- modelu gruntu,
- modelu odzysku ciepła,
- sposobu wyznaczania diagnostycznej i projektowej mocy cieplnej.

Frontend odróżnia `INFO`, `UWAGA`, `OK` i rzeczywiste niezaliczone kontrole.

## Elementy uzupełnione w normatywnym modelu godzinowym v2

### Grunt

Dodano osobny moduł `ground_iso13370.py`.

Dla podłogi na gruncie wykorzystuje on geometrię `A/P`, parametry cieplne gruntu,
opór warstw podłogi i grubość ściany zewnętrznej do wyznaczenia stacjonarnego
współczynnika przenikania. Do solvera 8760 h dołączany jest indywidualny profil
okresowej granicy gruntowej dla każdej przegrody.

Tryb formalny nie generuje arbitralnych współczynników okresowych. Wymaga jawnej
pary `periodic_amplitude_ratio` i `phase_shift_days` pochodzącej ze zweryfikowanej
procedury dynamicznej. Dostępny poza trybem formalnym model jednowymiarowej fali
cieplnej jest oznaczany jako diagnostyczny.

### Rekuperacja

Dodano szczegółowy model godzinowy rekuperacji:

- pełny fizyczny strumień wentylacyjny pozostaje w `Hve`,
- odzysk zmienia godzinową temperaturę nawiewu,
- można podać krzywą sprawności urządzenia,
- działa bypass letni,
- działa detekcja ryzyka szronienia,
- dostępne są strategie preheater / redukcja odzysku / wyłączenie odzysku,
- energia elektryczna nagrzewnicy wstępnej zwiększa `Ek`, `Ep` i emisję CO2,
- jedna centralna nagrzewnica nie jest mnożona przez liczbę stref.

Tryb formalny wymaga źródła charakterystyki urządzenia. Przy aktywnej ochronie
przeciwzamrożeniowej wymaga również jawnej wilgotności powietrza wywiewanego.

### Moc projektowa

Dodano osobny `design_load.py`, który nie korzysta z minimum TMY i nie używa
COP/sprawności generatora do wyznaczania mocy budynku.

Projektowe obciążenie cieplne korzysta z:

- jawnej projektowej temperatury zewnętrznej,
- własnych temperatur projektowych dla przestrzeni nieogrzewanych,
- własnych temperatur projektowych dla przegród do gruntu,
- strat przez mostki,
- wentylacji i szczegółowej rekuperacji,
- opcjonalnej jawnej mocy ponownego nagrzania.

Wynik projektowy jest raportowany osobno od rocznego bilansu. `Eu`, `Ek` i `Ep`
nadal wynikają z modelu godzinowego 8760 h.

### Ślad prawny i źródłowy

Dodano `legal.certificate_mode`. Tryb formalny wymaga:

- daty obliczenia,
- źródła metodologii,
- źródła danych klimatycznych,
- źródła współczynnika `wi` dla każdego używanego nośnika.

Dzięki temu wartości tabelaryczne, dane dostawcy i dane urządzeń nie są
nierozróżnialnymi liczbami w jednym formularzu.

## Granice, których nadal nie wolno ukrywać

### Pełny tekst norm

Repozytorium nie zawiera chronionej pełnej treści norm PKN/ISO. Tam, gdzie
formalna procedura dynamiczna wymaga współczynników, których nie da się
bezpiecznie odtworzyć z publicznego zakresu normy, aplikacja wymaga ich jawnego
podania wraz ze źródłem. Nie należy na tej podstawie twierdzić, że kod sam w
sobie dowodzi zgodności każdej klauzuli normy.

### Wilgotność

Model frost protection korzysta z jawnej wilgotności względnej powietrza
wywiewanego i punktu rosy. Nie jest to pełny model bilansu masowego wilgoci w
budynku. Pełny bilans wymagałby dodatkowych danych o emisji wilgoci, sorpcji,
nawilżaniu i osuszaniu, których silnik nie zgaduje.

### Klimat

Tryb formalny wymaga zapisania źródła danych klimatycznych. Sam identyfikator
stacji lub obecność pliku TMY nie oznacza automatycznie, że zestaw jest właściwy
dla danego celu i daty sporządzenia charakterystyki.

## Testy regresyjne

`backend/tests/test_audited_preflight.py` i
`backend/tests/test_normative_extensions.py` sprawdzają m.in.:

- odejmowanie okna od ściany brutto,
- zmianę Htr dokładnie o `Uw - Uwall` przy +1 m² okna,
- blokadę powierzchni transparentnej większej od hosta,
- blokadę niejednoznacznego hosta,
- jawne rozwiązanie niejednoznaczności przez `metadata.opening_hosts`,
- ostrzeżenia dla modelu `Af=150 m²`, dach/podłoga=90 m² i tylko N/S,
- pierwszeństwo `height × width` przed ręcznym `area`,
- udział wszystkich obsługiwanych nośników odnawialnych w `Uoze`,
- charakterystyczny wymiar gruntu `B'=2A/P`,
- monotoniczność izolacji podłogi i `U`,
- parę współczynników okresowych gruntu,
- analityczne przypadki odzysku, bypassu i preheatera,
- zachowanie fizycznego strumienia wentylacyjnego,
- brak mnożenia preheatera przez liczbę stref,
- niezależność obciążenia projektowego od COP,
- wymóg jawnej temperatury projektowej gruntu,
- wymogi śladu źródłowego trybu formalnego.
