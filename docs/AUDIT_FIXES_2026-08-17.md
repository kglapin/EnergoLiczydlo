# Audyt obliczeń — poprawki z 17 sierpnia 2026 r.

Ten dokument opisuje najważniejsze zmiany wprowadzone po audycie kompletności i spójności obliczeń charakterystyki energetycznej.

## 1. Powierzchnie ścian i otworów

Przegrody przezroczyste, takie jak okna, drzwi przeszklone i świetliki, są przed obliczeniem przypisywane do odpowiedniej przegrody nieprzezroczystej.

Powierzchnia nieprzezroczysta ściany jest liczona jako:

```text
powierzchnia netto ściany
=
powierzchnia brutto ściany
-
suma powierzchni przypisanych otworów
```

Dzięki temu okno zastępuje fragment ściany, zamiast być liczone dodatkowo na pełnej powierzchni ściany.

Model jest odrzucany, jeżeli:

- łączna powierzchnia otworów przekracza powierzchnię brutto przegrody, do której należą,
- otwór nie ma odpowiadającej mu przegrody zewnętrznej,
- otwór pasuje do kilku przegród i nie można jednoznacznie ustalić właściwej przegrody nadrzędnej.

Jeżeli kilka segmentów ściany ma tę samą orientację i nachylenie, użytkownik może wskazać właściwą przegrodę w `metadata.opening_hosts`.

## 2. Kontrola kompletności geometrii

Przed obliczeniem wykonywana jest kontrola geometrii projektu.

Program może zgłosić ostrzeżenie między innymi w przypadku:

- braku dachu albo innej górnej granicy strefy,
- braku podłogi albo innej dolnej granicy strefy,
- dużej różnicy między powierzchnią strefy a powierzchnią dachu lub podłogi,
- podejrzanie małej liczby kierunków ścian zewnętrznych,
- dużej różnicy między wysokością wynikającą z kubatury i powierzchni a wysokościami podanych ścian.

Są to ostrzeżenia, a nie automatyczne błędy, ponieważ nieregularna geometria budynku może być poprawna.

## 3. Założenia dotyczące instalacji

Raport wskazuje sytuacje, w których wynik może zależeć od niepełnych danych instalacyjnych.

Dotyczy to między innymi:

- braku rodzaju instalacji ogrzewania potrzebnego do wyznaczenia energii pomp obiegowych,
- systemu ciepłej wody użytkowej z zasobnikiem bez danych potrzebnych do wyznaczenia strat postojowych,
- braku wprowadzonych mostków cieplnych.

Brak mostków cieplnych oznacza w obliczeniu przewodność mostków równą `0 W/K`. Program nie powinien przedstawiać takiego wyniku jako automatycznie potwierdzonego założenia projektowego.

## 4. Udział odnawialnych nośników energii

Poprawiono sposób obliczania udziału energii odnawialnej.

Uwzględniane są obsługiwane odnawialne nośniki, w tym:

- biomasa,
- biogaz,
- energia słoneczna,
- energia wiatru,
- energia geotermalna.

Nazwy techniczne używane wewnątrz kodu mogą pozostać angielskie, ale w interfejsie użytkownik powinien widzieć polskie nazwy nośników.

## 5. Informacje i ostrzeżenia w wyniku

Wynik zawiera dodatkowe informacje dotyczące między innymi:

- przyjętego strumienia wentylacyjnego,
- infiltracji,
- zastosowanego współczynnika nakładu nieodnawialnej energii pierwotnej,
- źródła współczynnika energii pierwotnej w trybie świadectwa,
- zastosowanego modelu gruntu,
- zastosowanego modelu odzysku ciepła,
- sposobu wyznaczenia projektowego obciążenia cieplnego.

Komunikaty powinny być opisane po polsku i wprost wskazywać, czy dana informacja jest:

- potwierdzoną kontrolą,
- ostrzeżeniem,
- informacją techniczną,
- błędem blokującym obliczenie.

## 6. Rozszerzony model wymiany ciepła z gruntem

Dodano osobny moduł `ground_iso13370.py`.

Dla podłogi stykającej się z gruntem model wykorzystuje między innymi:

- powierzchnię podłogi,
- obwód wystawiony na wymianę z gruntem,
- właściwości cieplne gruntu,
- opór cieplny warstw podłogi,
- grubość ściany zewnętrznej.

Dla analizy godzinowej można również podać:

- współczynnik tłumienia rocznej zmiany temperatury,
- przesunięcie czasowe odpowiedzi gruntu.

W trybie wymagającym zweryfikowanych danych program nie tworzy tych parametrów z arbitralnych stałych.

## 7. Wentylacja z odzyskiem ciepła

Dodano szczegółowy godzinowy model odzysku ciepła.

Najważniejsze zmiany:

- pełny fizyczny strumień powietrza pozostaje w obliczeniu,
- odzysk ciepła zmienia temperaturę nawiewu,
- można podać charakterystykę sprawności urządzenia,
- można modelować letnie obejście wymiennika,
- można uwzględniać ryzyko zamarzania wymiennika,
- można wybrać nagrzewnicę wstępną, ograniczenie odzysku albo czasowe wyłączenie odzysku,
- energia elektryczna nagrzewnicy wstępnej zwiększa energię końcową i może zwiększać nieodnawialną energię pierwotną,
- moc jednego centralnego urządzenia nie jest mnożona przez liczbę stref.

Jeżeli wynik ma być formalnie kontrolowany, należy wskazać źródło charakterystyki zastosowanego urządzenia.

## 8. Projektowe obciążenie cieplne

Dodano osobny moduł `design_load.py`.

Projektowe obciążenie cieplne:

- nie jest wyznaczane z najniższej temperatury występującej w typowym roku meteorologicznym,
- nie zależy od współczynnika COP pompy ciepła ani sprawności kotła,
- korzysta z jawnej projektowej temperatury zewnętrznej,
- może korzystać z osobnych temperatur projektowych dla gruntu i przestrzeni nieogrzewanych,
- uwzględnia straty przez przenikanie, mostki cieplne i wentylację,
- może uwzględniać dodatkową moc potrzebną do ponownego nagrzania pomieszczeń.

Wynik jest raportowany jako osobna moc projektowa i nie jest dodawany do rocznej energii użytkowej.

## 9. Formalna charakterystyka energetyczna i analiza godzinowa

Po rozbudowie aplikacja utrzymuje dwa równoległe wyniki energetyczne:

1. **formalną charakterystykę energetyczną** liczoną miesięcznie zgodnie z polską metodologią,
2. **godzinową analizę fizyczną** obejmującą 8760 godzin roku.

Jeżeli włączony jest tryb świadectwa, główne formalne wartości:

- energia użytkowa (`Eu`),
- energia końcowa (`Ek`),
- nieodnawialna energia pierwotna (`Ep`)

pochodzą z miesięcznego silnika formalnej charakterystyki energetycznej.

Wynik godzinowy jest zachowywany jako osobna analiza techniczna i kontrolna.

## 10. Ślad źródłowy formalnego obliczenia

Tryb świadectwa zapisuje między innymi:

- datę wykonania obliczenia,
- zastosowaną metodologię,
- źródło danych klimatycznych,
- źródło miesięcznych współczynników wykorzystania zysków i strat,
- źródło danych i współczynników wentylacyjnych,
- źródło współczynnika nakładu nieodnawialnej energii pierwotnej dla każdego używanego nośnika.

Dzięki temu liczba użyta w obliczeniu nie jest oderwana od dokumentu lub danych, z których pochodzi.

## 11. Zasada blokowania formalnego wyniku przy brakujących danych

W trybie świadectwa brak wymaganej informacji nie powinien uruchamiać nieudokumentowanej wartości zastępczej.

Jeżeli nie można bezpiecznie wykonać formalnego obliczenia, program powinien wskazać brakujące dane i zatrzymać wynik formalny.

## 12. Granice modelu

### Pełne teksty norm

Repozytorium nie zawiera pełnych, chronionych tekstów norm PKN i ISO.

Jeżeli formalna procedura wymaga wartości, której nie można bezpiecznie wyznaczyć na podstawie dostępnych danych, aplikacja wymaga jej jawnego podania wraz ze źródłem.

### Wilgotność

Model ochrony wymiennika przed zamarzaniem może korzystać z jawnie podanej wilgotności względnej i temperatury punktu rosy.

Nie jest to jednak pełny godzinowy bilans masowy wilgoci całego budynku.

### Dane klimatyczne

Typowy rok meteorologiczny używany w analizie godzinowej i dane klimatyczne używane w formalnym świadectwie są traktowane jako oddzielne źródła danych.

Nie należy automatycznie zakładać, że jeden zestaw danych jest właściwy dla obu zastosowań.

## 13. Testy regresyjne

Testy obejmują między innymi:

- odejmowanie powierzchni okna od powierzchni brutto ściany,
- poprawną zmianę przewodności cieplnej po zastąpieniu części ściany oknem,
- blokowanie otworu większego od przegrody nadrzędnej,
- blokowanie niejednoznacznego przypisania otworu,
- kontrolę kompletności geometrii,
- udział odnawialnych nośników energii,
- charakterystyczny wymiar podłogi na gruncie,
- wpływ oporu cieplnego podłogi,
- godzinowy odzysk ciepła,
- letnie obejście wymiennika,
- ochronę przed zamarzaniem,
- brak wielokrotnego liczenia jednej nagrzewnicy centralnej,
- niezależność projektowego obciążenia cieplnego od współczynnika COP źródła,
- wymaganie jawnej projektowej temperatury gruntu,
- wymagania formalnego śladu źródłowego,
- rozdzielenie formalnego wyniku miesięcznego i analizy godzinowej 8760 godzin.
