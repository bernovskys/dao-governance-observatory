# Atkārtošana GitHub Actions

Šī pakotne sagatavota repozitorijam bernovskys/dao-governance-observatory.
Kopējiet .github/ un verification/ repozitorija atsevišķā zarā un palaidiet
Actions → Verify combined DAO dataset → Run workflow.
Pašreizējā pārbaude veikta mākoņvidē ar GitHub avota kodu; šī darbplūsma vēl nav palaista GitHub Actions.

Ievades Excel ir sākotnējais fails ar publiskām blokķēdes adresēm.
Pirms šīs pakotnes publicēšanas izvērtējiet, vai vēlaties publicēt arī sākotnējās datu lapas.
Rezultātu Excel un CSV neiekļauj individuālo adrešu sarakstus.
API kešatmiņa satur tikai pieprasījumiem vajadzīgos publiskos priekšlikumu un balssvara laukus.

Skripti atstāj oriģinālo Excel un repozitorija aprēķinu kodu nemainītus.
Iekļauti sākotnējie gaidītie skaitļi, izņēmumu saraksts un lietotāja verifikācijas skripts.
Skatiet rezultātu lapu Parbaudes_tverums: nevar apgalvot visu atsauces lapu neatkarīgu pārbaudi.
Ja ir API kļūdas vai nepilns balsojumu pārklājums, gala izveide apstājas un saglabā diagnostikas CSV.
