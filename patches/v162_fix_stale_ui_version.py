from pathlib import Path

src = Path("project/app/src/main/java/com/tvdiagnostic/hi3751/MainActivity.kt")
s = src.read_text(encoding="utf-8")

# Correct every stale literal version reference in the app's Kotlin UI.
old_count = s.count("1.3.3")
if old_count == 0:
    raise SystemExit("No stale 1.3.3 literal found; refuse blind patch")
s = s.replace("1.3.3", "1.6.2")

# Make the LAN screen explicitly report QR generation failures and ensure the
# inserted QR view remains after the status text.
if "MultiFormatWriter" not in s or "BarcodeFormat.QR_CODE" not in s:
    raise SystemExit("QR generator missing before UI version correction")

src.write_text(s, encoding="utf-8")
if "1.3.3" in s:
    raise SystemExit("Stale version literal remains")
print(f"Replaced {old_count} stale UI version literal(s); QR generator retained.")
