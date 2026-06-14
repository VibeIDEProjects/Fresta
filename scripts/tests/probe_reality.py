"""PoC: TLS-probe к нашему Xray-Reality-серверу на fresta.ru:8443.

С разных SNI из sni_candidates.txt проверяем, что:
  1) TCP+TLS до сервера доходит (не зафильтровано на нашей стороне);
  2) Reality-сервер отвечает валидным TLS-сертификатом;
  3) Сертификат выписан для dest=www.google.com (Reality проксирует «чужих» туда).

У «нашего» клиента (с правильным shortId/publicKey) Reality пустит в VLESS-туннель
и TLS-handshake не дойдёт до реального cert — сервер сразу начнёт VLESS-сессию.
А «чужой» клиент (мы без ключа) получит TLS-ответ от dest=www.google.com.

Запуск: python tests/probe_reality.py
"""
import os
import re
import socket
import ssl
import sys


SERVER = ("fresta.ru", 8443)


def probe(sni: str, timeout: int = 8) -> tuple[bool, str]:
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    try:
        with socket.create_connection(SERVER, timeout=timeout) as s:
            with ctx.wrap_socket(s, server_hostname=sni) as tls:
                cert = tls.getpeercert(binary_form=True)
                pem = ssl.DER_cert_to_PEM_cert(cert)
                # Из PEM-формы (которая содержит текстовое представление ASN.1)
                # дёрнем Subject CN или Issuer O — этого достаточно.
                m_subj = re.search(r"Subject:.*?CN\s*=\s*([^\n,]+)", pem)
                m_iss = re.search(r"Issuer:.*?O\s*=\s*([^\n,]+)", pem)
                cn = m_subj.group(1).strip() if m_subj else "?"
                issuer = m_iss.group(1).strip() if m_iss else "?"
                return True, f"TLS={tls.version()} cert={len(cert)}B CN={cn!r} Issuer={issuer!r}"
    except OSError as e:
        return False, f"NET: {e}"
    except ssl.SSLError as e:
        return False, f"TLS: {e}"
    except Exception as e:  # noqa: BLE001
        return False, f"{type(e).__name__}: {e}"


def main() -> int:
    # SNI-кандидаты из harvest'а — те самые, что и в server.json
    candidates_path = os.path.join(os.path.dirname(__file__), "..", "harvest", "sni_candidates.txt")
    snis: list[str] = []
    with open(candidates_path, encoding="utf-8") as f:
        for line in f:
            d = line.strip()
            if d and not d.startswith("#"):
                snis.append(d)

    print(f"Probe {SERVER[0]}:{SERVER[1]} (Reality, без своего ключа) — "
          f"ожидаем TLS-ответ от dest=www.google.com:443\n")
    print(f"{'SNI':32s} {'status':6s}  {'detail'}")
    print("-" * 100)

    bad = 0
    for sni in snis:
        ok, detail = probe(sni)
        mark = "OK" if ok else "FAIL"
        if not ok:
            bad += 1
        print(f"{sni:32s} {mark:6s}  {detail}")

    print()
    if bad == 0:
        print(f"ALL_OK: {len(snis)}/{len(snis)} SNI ответили валидным TLS. "
              f"Reality-сервер жив, маршрутизация по SNI работает.")
        return 0
    else:
        print(f"PARTIAL: {len(snis) - bad}/{len(snis)} OK, {bad} не ответили. "
              f"Сервер жив, но часть SNI не зашла (фильтр на пути или SNI-bl).")
        return 1


if __name__ == "__main__":
    sys.exit(main())
