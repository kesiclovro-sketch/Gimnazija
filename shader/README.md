# Chronochrome

WebGL shader koji mijenja boje ovisno o vremenu proteklom od pokretanja.

- `index.html` — samostalna stranica, bez buildanja i bez ovisnosti. Otvori je izravno u pregledniku ili je posluži bilo kojim statičkim serverom (`python3 -m http.server`).
- Tri načina: **Spektar** (ton se ravnomjerno vrti s `u_time`), **Plazma** (zbroj sinusa pomaknutih u vremenu), **Aurora** (dvostruko savijanje domene fbm šumom).
- Kontrole: brzina (0–3×), pauza, reset štoperice, skrivanje HUD-a (ili dvoklik / dvostruki dodir na platno).
- Povlačenje prstom/mišem pomiče `u_ptr`, žarište uzorka.
- HUD ispisuje žive vrijednosti uniformi (`u_time`, `u_res`, `u_ptr`) i hex boje središnjeg piksela.

Uz `prefers-reduced-motion` stranica kreće pauzirana i na manjoj brzini.
