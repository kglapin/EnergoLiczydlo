# Audyt obliczeń — poprawki 2026-08-17

Ten dokument opisuje zmiany wprowadzone po audycie kompletności i spójności obliczeń charakterystyki energetycznej.

## Zaimplementowane zabezpieczenia

### Powierzchnie brutto/netto

Przegrody transparentne są przed obliczeniem przypisywane do jednoznacznej przegrody zewnętrznej w tej samej strefie, o tej samej orientacji i nachyleniu. Powierzchnia okien/drzwi/skylightów jest odejmowana od powierzchni brutto przegrody nieprzezroczystej. Dzięki temu dodanie 1 m² okna zmienia Htr o `Uw - Uwall`, a nie o samo `Uw`.

Model jest odrzucany, jeżeli:

- powierzchnia otworów przekracza powierzchnię brutto hosta,
- otwór nie ma odpowiadającej mu przegrody zewnętrznej,
- otwór pasuje do więcej niż jednej przegrody i przypisanie jest niejednoznaczne.

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

`Uoze` uwzględnia obecnie wszystkie obsługiwane odnawialne nośniki energii końcowej:

- biomass,
- biogas,
- solar,
- wind,
- geothermal,
- legacy `renewable`.

### Raport założeń

Wyniki zawierają osobne informacje/ostrzeżenia audytowe dotyczące m.in.:

- wartości wejściowych wentylacji i infiltracji,
- współczynnika energii pierwotnej energii elektrycznej,
- uproszczonego modelu gruntu,
- stałej sprawności odzysku ciepła,
- sposobu wyznaczania diagnostycznej mocy szczytowej.

Frontend odróżnia `INFO`, `UWAGA`, `OK` i rzeczywiste niezaliczone kontrole.

## Ograniczenia, których nie wolno ukrywać

### Grunt

Obecny silnik nadal nie implementuje pełnego PN-EN ISO 13370. Używa okresowego modelu temperatury gruntu opisanego w `METHODOLOGY.md`. Pełna implementacja wymaga dodatkowych danych geometrycznych i normowych (m.in. parametrów równoważnej płyty/perymetru) i powinna zostać wdrożona jako osobny model zamiast zgadywania brakujących wartości.

### Rekuperacja

Sprawność odzysku jest obecnie stałą wartością sezonową. Nie ma pełnego modelu bypassu letniego, oszraniania ani krzywych producenta. Silnik raportuje to jawnie jako ograniczenie.

### Moc projektowa

`design_heating_power_kw` pozostaje maksimum strat z godzin wybranego TMY. Interfejs nie nazywa już tej wartości formalnym „doborem mocy źródła”. Pełne obciążenie projektowe wymaga osobnej temperatury obliczeniowej i procedury projektowej.

## Testy regresyjne

`backend/tests/test_audited_preflight.py` sprawdza m.in.:

- odejmowanie okna od ściany brutto,
- zmianę Htr dokładnie o `Uw - Uwall` przy +1 m² okna,
- blokadę powierzchni transparentnej większej od hosta,
- blokadę niejednoznacznego hosta,
- ostrzeżenia dla modelu `Af=150 m²`, dach/podłoga=90 m² i tylko N/S,
- pierwszeństwo `height × width` przed ręcznym `area`,
- ostrzeżenia o brakującej klasyfikacji instalacji, stratach zasobnika i mostkach,
- poprawny udział wszystkich obsługiwanych nośników odnawialnych w `Uoze`.
