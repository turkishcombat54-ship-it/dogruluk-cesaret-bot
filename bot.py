import asyncio
import random
import os
import json
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command

TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
if not TOKEN:
    raise RuntimeError("TELEGRAM_BOT_TOKEN ortam değişkeni ayarlanmamış!")

bot = Bot(token=TOKEN)
dp = Dispatcher()

players = []
game_open = False
game_running = False
thread_id = None

current_player_id = None
waiting_for_choice = False
player_choice = None

SORULAR_DOSYA = "sorular.json"
SECIM_TIMEOUT = 30


def sorulari_yukle():
    try:
        with open(SORULAR_DOSYA, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"dogruluk": [], "cesaret": []}


def sorulari_kaydet(data):
    with open(SORULAR_DOSYA, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


async def grup_mesaj(chat_id, metin, **kwargs):
    await bot.send_message(chat_id, metin, message_thread_id=thread_id, parse_mode="HTML", **kwargs)


# ─── Soru yönetimi ────────────────────────────────────────────

@dp.message(Command("dogruluk_ekle"))
async def dogruluk_ekle(message: types.Message):
    metin = message.text.removeprefix("/dogruluk_ekle").strip()
    if not metin:
        await message.answer("❗ Kullanım: /dogruluk_ekle <soru metni>")
        return
    data = sorulari_yukle()
    data["dogruluk"].append(metin)
    sorulari_kaydet(data)
    await message.answer(f"✅ Doğruluk sorusu eklendi!\n🧠 <i>{metin}</i>", parse_mode="HTML")


@dp.message(Command("cesaret_ekle"))
async def cesaret_ekle(message: types.Message):
    metin = message.text.removeprefix("/cesaret_ekle").strip()
    if not metin:
        await message.answer("❗ Kullanım: /cesaret_ekle <görev metni>")
        return
    data = sorulari_yukle()
    data["cesaret"].append(metin)
    sorulari_kaydet(data)
    await message.answer(f"✅ Cesaret görevi eklendi!\n🔥 <i>{metin}</i>", parse_mode="HTML")


@dp.message(Command("listele"))
async def listele(message: types.Message):
    data = sorulari_yukle()
    msg = "📋 <b>Mevcut Sorular</b>\n\n"
    msg += "🧠 <b>Doğruluk Soruları:</b>\n"
    if data["dogruluk"]:
        for i, s in enumerate(data["dogruluk"], 1):
            msg += f"  {i}. {s}\n"
    else:
        msg += "  <i>(Henüz soru yok)</i>\n"
    msg += "\n🔥 <b>Cesaret Görevleri:</b>\n"
    if data["cesaret"]:
        for i, s in enumerate(data["cesaret"], 1):
            msg += f"  {i}. {s}\n"
    else:
        msg += "  <i>(Henüz görev yok)</i>\n"
    await message.answer(msg, parse_mode="HTML")


@dp.message(Command("sil"))
async def sil(message: types.Message):
    parcalar = message.text.removeprefix("/sil").strip().split()
    if len(parcalar) != 2:
        await message.answer("❗ Kullanım:\n/sil d <numara> — doğruluk sil\n/sil c <numara> — cesaret sil")
        return
    tur, num_str = parcalar
    tur = tur.lower()
    if tur not in ("d", "c"):
        await message.answer("❗ Tür 'd' (doğruluk) veya 'c' (cesaret) olmalı.")
        return
    try:
        num = int(num_str)
    except ValueError:
        await message.answer("❗ Numara tam sayı olmalı.")
        return
    data = sorulari_yukle()
    liste = data["dogruluk"] if tur == "d" else data["cesaret"]
    if num < 1 or num > len(liste):
        await message.answer(f"❗ Geçersiz numara. 1 ile {len(liste)} arasında olmalı.")
        return
    silinen = liste.pop(num - 1)
    sorulari_kaydet(data)
    tur_ad = "Doğruluk sorusu" if tur == "d" else "Cesaret görevi"
    await message.answer(f"🗑️ {tur_ad} silindi:\n<i>{silinen}</i>", parse_mode="HTML")


# ─── Oyun akışı ───────────────────────────────────────────────

async def oyun_baslat(chat_id: int):
    global players, game_open, game_running, thread_id

    await asyncio.sleep(15)
    game_open = False

    if len(players) < 2:
        game_running = False
        await grup_mesaj(chat_id, "❌ Yeterli oyuncu yok. En az 2 kişi gerekli.")
        return

    isimler = ", ".join(p["name"] for p in players)
    await grup_mesaj(chat_id, f"🔥 <b>Oyun başladı!</b>\nOyuncular: {isimler}")
    await game_loop(chat_id)


async def game_loop(chat_id):
    global players, game_running, thread_id, current_player_id, waiting_for_choice, player_choice

    for tur in range(1, 100):
        if not game_running or len(players) < 2:
            break

        data = sorulari_yukle()
        havuz = []
        if data["dogruluk"]:
            havuz.append("d")
        if data["cesaret"]:
            havuz.append("c")

        if not havuz:
            await grup_mesaj(chat_id, "❗ Soru/görev kalmadı, oyun bitti!")
            break

        secilen = random.choice(players)
        current_player_id = secilen["id"]
        waiting_for_choice = True
        player_choice = None

        await grup_mesaj(
            chat_id,
            f"🎯 <b>Tur {tur}</b>\n\n"
            f"👤 <b>{secilen['name']}</b>, sıra sende!\n"
            f"<b>Doğruluk</b> mu <b>Cesaret</b> mi? Yaz!"
        )

        for _ in range(SECIM_TIMEOUT):
            await asyncio.sleep(1)
            if not waiting_for_choice:
                break

        if waiting_for_choice:
            waiting_for_choice = False
            current_player_id = None
            await grup_mesaj(chat_id, f"⏰ <b>{secilen['name']}</b> {SECIM_TIMEOUT} saniyede cevap vermedi, sıra geçiliyor.")
            await asyncio.sleep(3)
            continue

        if player_choice == "d":
            if not data["dogruluk"]:
                await grup_mesaj(chat_id, "❗ Doğruluk sorusu yok!")
            else:
                soru = random.choice(data["dogruluk"])
                await grup_mesaj(
                    chat_id,
                    f"🧠 <b>Doğruluk sorusu:</b>\n{soru}"
                )
        else:
            if not data["cesaret"]:
                await grup_mesaj(chat_id, "❗ Cesaret görevi yok!")
            else:
                gorev = random.choice(data["cesaret"])
                await grup_mesaj(
                    chat_id,
                    f"🔥 <b>Cesaret görevi:</b>\n{gorev}"
                )

        await asyncio.sleep(20)

        if not game_running:
            break

        if tur >= 10:
            await grup_mesaj(
                chat_id,
                "🏁 <b>Oyun bitti!</b> 10 tur tamamlandı.\nTekrar oynamak için /oyun yazın."
            )
            break

    game_running = False
    current_player_id = None
    waiting_for_choice = False


@dp.message(Command("oyun"))
async def oyun(message: types.Message):
    global players, game_open, game_running, thread_id

    if game_open or game_running:
        await message.answer("⚠️ Zaten devam eden bir oyun var!")
        return

    data = sorulari_yukle()
    if not data["dogruluk"] and not data["cesaret"]:
        await message.answer(
            "❗ Hiç soru/görev eklenmemiş!\n\n"
            "Önce soru ekle:\n"
            "/dogruluk_ekle <soru>\n"
            "/cesaret_ekle <görev>"
        )
        return

    players = []
    game_open = True
    game_running = True
    thread_id = message.message_thread_id

    await message.answer(
        "🎮 <b>Doğruluk mu Cesaret mi</b> başlıyor!\n\n"
        "⏳ 15 saniye içinde <b>katıl</b> yazarak oyuna katıl!",
        parse_mode="HTML"
    )

    asyncio.create_task(oyun_baslat(message.chat.id))


@dp.message(Command("bitir"))
async def bitir(message: types.Message):
    global players, game_open, game_running, waiting_for_choice, current_player_id

    if not game_running and not game_open:
        await message.answer("⚠️ Şu an aktif bir oyun yok.")
        return

    member = await bot.get_chat_member(message.chat.id, message.from_user.id)
    if member.status not in ("administrator", "creator"):
        await message.answer("❌ Bu komutu sadece grup adminleri kullanabilir.")
        return

    game_running = False
    game_open = False
    waiting_for_choice = False
    current_player_id = None
    players = []
    await message.answer("🛑 <b>Oyun admin tarafından sonlandırıldı.</b>", parse_mode="HTML")


@dp.message(Command("oyuncular"))
async def oyuncular(message: types.Message):
    if not game_running and not game_open:
        await message.answer("⚠️ Şu an aktif bir oyun yok.")
        return
    if not players:
        await message.answer("👥 Henüz kimse katılmadı.")
        return
    liste = "\n".join(f"  {i}. {p['name']}" for i, p in enumerate(players, 1))
    durum = "Katılım aşamasında" if game_open else "Oyun devam ediyor"
    await message.answer(
        f"👥 <b>Oyuncular ({durum}):</b>\n{liste}",
        parse_mode="HTML"
    )


@dp.message(Command("yardim"))
async def yardim(message: types.Message):
    await message.answer(
        "📖 <b>Komutlar</b>\n\n"
        "🎮 <b>Oyun</b>\n"
        "/oyun — Oyunu başlat\n"
        "<code>katıl</code> — Oyuna katıl (oyun açıkken)\n"
        "/oyuncular — Oyundaki kişileri gör\n"
        "/bitir — Oyunu erken bitir (sadece admin)\n\n"
        "➕ <b>Soru Ekle</b>\n"
        "/dogruluk_ekle <i>soru metni</i>\n"
        "/cesaret_ekle <i>görev metni</i>\n\n"
        "📋 <b>Listele / Sil</b>\n"
        "/listele — Tüm soruları gör\n"
        "/sil d <i>numara</i> — Doğruluk sorusunu sil\n"
        "/sil c <i>numara</i> — Cesaret görevini sil",
        parse_mode="HTML"
    )


@dp.message()
async def mesaj_handler(message: types.Message):
    global players, game_open, waiting_for_choice, current_player_id, player_choice

    text = message.text
    if not text:
        return

    text_lower = text.lower().strip()

    # Katılma
    if game_open and text_lower == "katıl":
        if message.from_user.id not in [p["id"] for p in players]:
            players.append({
                "id": message.from_user.id,
                "name": message.from_user.first_name or message.from_user.username or "Bilinmeyen"
            })
            await message.answer(
                f"✅ <b>{message.from_user.first_name}</b> oyuna katıldı!",
                parse_mode="HTML"
            )
        return

    # Doğruluk / Cesaret seçimi
    if waiting_for_choice and message.from_user.id == current_player_id:
        if text_lower in ("doğruluk", "dogruluk", "d"):
            player_choice = "d"
            waiting_for_choice = False
            await message.answer("🧠 <b>Doğruluk</b> seçtin!", parse_mode="HTML")
        elif text_lower in ("cesaret", "c"):
            player_choice = "c"
            waiting_for_choice = False
            await message.answer("🔥 <b>Cesaret</b> seçtin!", parse_mode="HTML")


async def main():
    print("Bot başlatılıyor...")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
