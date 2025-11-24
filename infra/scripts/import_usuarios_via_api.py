#!/usr/bin/env python3
import csv, sys, time, argparse, requests

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("csv_path")
    ap.add_argument("--base", default="http://localhost:8000")
    ap.add_argument("--user", default="dev@local")
    ap.add_argument("--password", default="123")
    ap.add_argument("--default-domain", default="agepar.pr.gov.br")
    ap.add_argument("--tipo", default="efetivo")
    ap.add_argument("--status", default="ativo")
    ap.add_argument("--out", default="import_result.csv")
    args = ap.parse_args()

    s = requests.Session()
    r = s.post(f"{args.base}/api/auth/login", json={"identifier": args.user, "password": args.password})
    r.raise_for_status()

    with open(args.csv_path, newline="", encoding="utf-8") as f,\
         open(args.out, "w", newline="", encoding="utf-8") as g:
        rd = csv.DictReader(f)
        wr = csv.writer(g)
        wr.writerow(["nome","cpf","email","user_id","temporary_pin","status","http_status","error"])

        for row in rd:
            nome = (row.get("NOMES") or row.get("nome") or "").strip()
            cpf = "".join(c for c in (row.get("CPF") or "") if c.isdigit())
            email = (row.get("E-MAIL") or row.get("email") or "").strip()
            if email and "@" not in email:
                email = f"{email}@{args.default_domain}"

            payload = {
                "nome_completo": nome,
                "cpf": cpf,
                "email_principal": email or None,
                "tipo_vinculo": args.tipo,
                "status": args.status
            }
            try:
                r = s.post(f"{args.base}/api/automations/usuarios/users", json=payload)
                code = r.status_code
                if code == 200:
                    data = r.json()
                    wr.writerow([nome, cpf, email, data.get("id",""), data.get("temporary_pin",""), "ok", code, ""])
                    print(f"OK  - {nome} ({cpf}) → id={data.get('id')} pin={data.get('temporary_pin')}")
                else:
                    try:
                        err = r.json()
                        msg = err.get("message") or err.get("detail") or str(err)
                    except Exception:
                        msg = r.text
                    wr.writerow([nome, cpf, email, "", "", "fail", code, msg])
                    print(f"FAIL- {nome} ({cpf}) → HTTP {code}: {msg}")
            except Exception as e:
                wr.writerow([nome, cpf, email, "", "", "fail", "", str(e)])
                print(f"ERR - {nome} ({cpf}) → {e}")
            time.sleep(0.1)

    print(f"Resultado salvo em: {args.out}")

if __name__ == "__main__":
    main()
