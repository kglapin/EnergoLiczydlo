# Metoda świadectwa w Polsce a model godzinowy ISO 52016

## Zasada nadrzędna

Aplikacja utrzymuje dwa różne poziomy obliczeń i nie utożsamia ich ze sobą:

1. **wynik formalny charakterystyki energetycznej w Polsce** — liczony metodą
   miesięczną wynikającą z załącznika nr 1 do rozporządzenia w sprawie
   metodologii wyznaczania charakterystyki energetycznej,
2. **szczegółowa analiza fizyczna 8760 h** — solver ISO 52016 wykorzystywany do
   analizy godzinowej temperatur, ogrzewania/chłodzenia, gruntu i pracy
   systemów.

Włączenie `metadata.normative.legal.certificate_mode` powoduje, że główne
`Eu`, `Ek`, `Ep` i tabela miesięczna pochodzą z polskiego silnika miesięcznego.
Wynik ISO 52016 nie znika — jest przechowywany jako analiza równoległa w
`hourly.normative_diagnostics.certificate.iso52016_hourly_analysis`.

## Dlaczego są dwa silniki

Metodologia świadectwa definiuje roczne zapotrzebowanie jako sumę miesięcznych
potrzeb energii. Dla ogrzewania bilans miesiąca ma postać:

```text
QH,nd,n = QH,ht,n - etaH,gn,n * QH,gn,n
```

z ograniczeniem do wartości dodatnich.

Dla chłodzenia analogicznie:

```text
QC,nd,n = QC,gn,n - etaC,ls,n * QC,ht,n
```

Dlatego wynik godzinowego solvera nie jest podstawiany w miejsce tych wzorów.
Może służyć do kontroli jakości, diagnostyki i analiz technologicznych, ale nie
jest automatycznie wynikiem ustawowej metody świadectwa.

## Dane miesięczne formalnego silnika

`metadata.normative.polish_certificate` zawiera m.in.:

- miesięczną temperaturę zewnętrzną,
- miesięczne promieniowanie na każdą przegrodę przezroczystą,
- miesięczne temperatury wewnętrzne dla ogrzewania/chłodzenia,
- `etaH,gn` — wykorzystanie zysków dla ogrzewania,
- `etaC,ls` — wykorzystanie strat dla chłodzenia,
- `beta` — udział czasu użytkowania,
- sprawność odzysku ciepła,
- współczynnik redukcji strumienia nawiewno-wywiewnego,
- temperatury przestrzeni nieogrzewanych i gruntu,
- gęstość zysków wewnętrznych,
- miesięczną energię elektryczną nagrzewnicy przeciwzamrożeniowej,
- opcjonalne zweryfikowane miesięczne `QH,nd` / `QC,nd` dla przypadków, których
  procedura szczegółowa wymaga zewnętrznego arkusza obliczeniowego.

Każda seria miesięczna ma dokładnie 12 wartości.

## Klimat

Tryb formalny wymaga potwierdzenia, że miesięczne dane klimatyczne pochodzą z
właściwego zestawu udostępnionego w Biuletynie Informacji Publicznej ministra
właściwego do spraw budownictwa oraz dotyczą odpowiedniej stacji
meteorologicznej.

Domyślny plik TMYx używany przez analizę godzinową nie jest automatycznie
przenoszony do formalnego silnika świadectwa.

## Współczynniki delegowane do Polskiej Normy

Jeżeli rozporządzenie wskazuje, że dany współczynnik należy wyznaczyć zgodnie z
Polską Normą, aplikacja nie odtwarza go z niezweryfikowanego wzoru ani z
pamięci implementacji.

W szczególności formalny silnik wymaga jawnych miesięcznych serii:

- `heating_gain_utilization_by_zone`,
- `cooling_loss_utilization_by_zone`.

Tryb formalny przechowuje również źródło tych współczynników w
`legal.utilization_factor_source`.

## Wentylacja

Formalny model miesięczny zachowuje rozdzielenie:

- strumienia podstawowego,
- udziału użytkowania `beta`,
- przepływu poza okresem użytkowania,
- infiltracji,
- współczynnika redukcji dla instalacji nawiewno-wywiewnej,
- odzysku ciepła.

Jeżeli projekt nie podaje wartości redukcji, stosowany jest przewidziany przez
metodologię fallback `rn = 0.75`, a wynik zawiera informację o tym fakcie.

Wartości odzysku ciepła wymagane przez formalny silnik są miesięcznymi danymi
projektowymi. Szczegółowa symulacja godzinowa rekuperatora pozostaje odrębną
analizą i nie jest niejawnie uśredniana do świadectwa.

## Nagrzewnica przeciwzamrożeniowa

Godzinowy model rekuperacji wyznacza energię nagrzewnicy na podstawie TMY i
pracy urządzenia. Ta energia jest wynikiem analitycznym.

Jeżeli formalny model świadectwa wykorzystuje nagrzewnicę, wymagana jest
odrębna 12-miesięczna seria
`preheater_electricity_kwh_by_month`. Dzięki temu dane z analizy TMY nie są
niejawnie mieszane z formalnymi danymi klimatycznymi świadectwa.

## Energia końcowa i pierwotna

Po wyznaczeniu miesięcznego `QH,nd`, `QC,nd` oraz rocznego `QW,nd` aplikacja
przelicza potrzeby na energię końcową z parametrów systemów technicznych, a
następnie na energię pierwotną z `wi`.

Dla `wi` formalny tryb przechowuje źródło każdej wartości. Jeżeli dla danego
nośnika dostępne są dane dostawcy, należy wprowadzić współczynnik właściwy dla
tego projektu. Wartość tabelaryczna powinna być jawnie opisana jako fallback,
gdy brak danych dostawcy.

## Projektowe obciążenie cieplne

Obciążenie projektowe pozostaje trzecim, niezależnym wynikiem:

- nie jest energią roczną,
- nie wpływa na `Eu`, `Ek`, `Ep`,
- nie korzysta z najzimniejszej godziny TMY,
- korzysta z jawnych projektowych warunków brzegowych.

## Zasada fail-closed

W trybie formalnym brak danych nie prowadzi do cichego przyjęcia wartości
uproszczonej. Obliczenie jest zatrzymywane, jeżeli brakuje m.in. wymaganych
danych klimatycznych, współczynników miesięcznych, danych formalnego modelu
gruntu, dokumentacji odzysku ciepła lub źródła `wi`.

Ta zasada jest celowa: lepszy jest brak wyniku formalnego niż wynik o pozornej
precyzji oparty na nieudokumentowanym fallbacku.
