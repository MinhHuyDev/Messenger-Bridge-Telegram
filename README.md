# Messenger Bridge Telegram

Messenger Bridge Telegram la bridge hai chieu giua Facebook Messenger va Telegram Forum Topics. Du an duoc viet bang Python, su dung `fbchat-v2` de listen/send Messenger, bao gom ca E2EE, va su dung `python-telegram-bot` de van hanh bot Telegram.

Moi hoi thoai Messenger duoc gan voi mot topic rieng trong Telegram supergroup. Tin nhan, reply, reaction va cac activity realtime se duoc dua vao dung topic, giup theo doi nhieu nhom/nguoi dung 1-1 trong cung mot group Telegram.

## Diem chinh

- Bridge hai chieu Messenger <-> Telegram.
- Tu dong tao Telegram forum topic cho hoi thoai Messenger moi.
- Ho tro regular Messenger va E2EE Messenger thong qua `fbchat-v2`.
- Forward tin nhan Messenger sang Telegram, giu mapping reply khi co message ID.
- Forward tin nhan Telegram trong topic nguoc ve Messenger.
- Hien realtime activity Messenger: reaction, go reaction, edit message, unsend, typing, read receipt va E2EE receipt.
- Gui Telegram sticker sang Messenger theo kha nang transport: static sticker nhu sticker/image, video/animated sticker nhu video/file best-effort.
- Luu mapping topic/message trong `data/bridge-store.json` de reply va activity co the bam dung tin goc.
- Tu recover khi Telegram topic bi xoa/dong va mapping bi stale.

## Kien truc

```text
Facebook Messenger
  -> fbchat-v2 listener / E2EE bridge
  -> src/messenger/client.py
  -> src/bridge.py
  -> python-telegram-bot
  -> Telegram supergroup forum topics
```

Thanh phan chinh:

| File | Vai tro |
|---|---|
| `src/main.py` | Entry point, load config va chay Telegram polling. |
| `src/config.py` | Doc `.env`, auto-detect `fbchat-v2/src` va E2EE binary local. |
| `src/messenger/client.py` | Dang nhap Messenger, listen E2EE/regular, gui text/sticker/media best-effort. |
| `src/messenger/events.py` | Chuan hoa raw event Messenger thanh message/activity model. |
| `src/bridge.py` | Dieu phoi hai chieu, tao topic, recover topic, retry Telegram network errors. |
| `src/store.py` | Luu mapping topic, message ID va quote data. |
| `src/tg/handlers.py` | Telegram commands va message handler. |
| `src/utils/formatting.py` | Format HTML message/activity cho Telegram. |

## Yeu cau

- Windows, Linux hoac macOS.
- Python 3.10 tro len. Du an da duoc chay voi Python 3.13.
- Telegram bot token tu BotFather.
- Telegram supergroup da bat Topics.
- Bot Telegram phai la admin va co quyen Manage Topics.
- Cookie Facebook cua tai khoan Messenger dung de bridge.
- `fbchat-v2` va binary `fbchat-bridge-e2ee.exe` neu can E2EE.
- Go 1.24 tro len neu can rebuild E2EE bridge binary.

## Cai dat nhanh

Trong PowerShell:

```powershell
cd "c:\Users\minhh\Downloads\mhwidev - project\Messenger-Bridge-Telegram"
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env
```

Sua file `.env` va dien cac gia tri bat buoc:

```env
TG_TOKEN=1234567890:replace_me
TG_GROUP_ID=-1001234567890
FACEBOOK_COOKIE=c_user=...; xs=...; fr=...; datr=...;
DATA_DIR=./data
```

Neu dung `fbchat-v2` local nam canh thu muc project, cau hinh nay thuong duoc auto-detect. Co the khai bao thu cong khi can:

```env
FBCHAT_V2_SRC_PATH=../fbchat-v2/src
FBCHAT_E2EE_BIN=../fbchat-v2/build/fbchat-bridge-e2ee.exe
```

## Cau hinh `.env`

| Bien | Bat buoc | Mo ta |
|---|---:|---|
| `TG_TOKEN` | Co | Token bot Telegram tu BotFather. |
| `TG_GROUP_ID` | Co | ID supergroup Telegram, thuong co dang `-100...`. |
| `FACEBOOK_COOKIE` | Co* | Cookie Facebook cua tai khoan Messenger. |
| `FACEBOOK_COOKIE_FILE` | Co* | Duong dan file chua cookie, dung thay cho `FACEBOOK_COOKIE`. |
| `DATA_DIR` | Khong | Thu muc luu `bridge-store.json`, mac dinh `./data`. |
| `FBCHAT_V2_SRC_PATH` | Khong | Duong dan den thu muc `fbchat-v2/src`. Project co auto-detect mot so vi tri local. |
| `FBCHAT_E2EE_BIN` | Khong | Duong dan den binary `fbchat-bridge-e2ee.exe`. |
| `FBCHAT_ENABLE_E2EE` | Khong | Bat/tat E2EE listener, mac dinh `1`. |
| `FBCHAT_E2EE_MEMORY_ONLY` | Khong | Luu key E2EE trong RAM, mac dinh `1`. |
| `FBCHAT_E2EE_DEVICE_PATH` | Khong | File persist device/key E2EE neu khong memory-only. |
| `FBCHAT_E2EE_LOG_LEVEL` | Khong | Log level cua bridge E2EE, mac dinh `none`. |
| `IGNORE_SELF_MESSAGES` | Khong | Bo qua tin do chinh tai khoan Facebook gui, mac dinh `1`. |
| `MESSAGE_CACHE_LIMIT` | Khong | So mapping message giu lai de reply/activity, mac dinh `3000`. |
| `TG_CONNECT_TIMEOUT` | Khong | Timeout ket noi Telegram Bot API, mac dinh `15`. |
| `TG_READ_TIMEOUT` | Khong | Timeout doc response Telegram Bot API, mac dinh `45`. |
| `TG_WRITE_TIMEOUT` | Khong | Timeout gui request Telegram Bot API, mac dinh `45`. |
| `TG_POOL_TIMEOUT` | Khong | Timeout cho connection pool Telegram, mac dinh `30`. |
| `FORWARD_TYPING_ACTIVITY` | Khong | Forward typing indicator sang Telegram. Mac dinh `0` de tranh spam. |
| `FORWARD_READ_RECEIPTS` | Khong | Forward read receipt sang Telegram. Mac dinh `0` de tranh spam. |

`FACEBOOK_COOKIE` va `FACEBOOK_COOKIE_FILE` la hai cach thay the nhau; chi can mot trong hai.

## Chuan bi Telegram group

1. Tao bot voi BotFather va copy token vao `TG_TOKEN`.
2. Tao Telegram group, convert thanh supergroup neu can.
3. Bat Topics trong group settings.
4. Them bot vao group.
5. Promote bot thanh admin.
6. Bat quyen Manage Topics va quyen gui tin nhan.
7. Lay group ID dang `-100...` va dien vao `TG_GROUP_ID`.

Sau khi chay bot, dung lenh `/checktopics` trong group de kiem tra quyen.

## Build E2EE binary

Neu da co `fbchat-v2/build/fbchat-bridge-e2ee.exe`, co the bo qua buoc nay. Neu chua co hoac vua sua RPC media/sticker, rebuild binary:

```powershell
cd "c:\Users\minhh\Downloads\mhwidev - project\fbchat-v2\bridge-e2ee"
go mod tidy
go build -ldflags="-s -w" -o ..\build\fbchat-bridge-e2ee.exe .
```

Sau do dam bao `.env` tro dung binary:

```env
FBCHAT_E2EE_BIN=../fbchat-v2/build/fbchat-bridge-e2ee.exe
```

## Chay bridge

```powershell
cd "c:\Users\minhh\Downloads\mhwidev - project\Messenger-Bridge-Telegram"
.\.venv\Scripts\Activate.ps1
python .\src\main.py
```

Khi bridge khoi dong thanh cong, bot se gui thong bao vao Telegram group. Khi co hoi thoai Messenger moi, bridge se tao topic moi va bat dau forward tin nhan/activity vao topic do.

## Lenh Telegram

| Lenh | Mo ta |
|---|---|
| `/help` | Hien thong tin su dung co ban. |
| `/status` | Xem trang thai listener, Facebook ID va so topic da map. |
| `/checktopics` | Kiem tra supergroup, Topics va quyen Manage Topics cua bot. |
| `/topic list` | Liet ke cac topic da map voi Messenger. |
| `/topic info` | Xem mapping cua topic hien tai. |
| `/topic delete` | Xoa mapping cua topic hien tai. |

Tin nhan va sticker Telegram chi duoc forward ve Messenger khi duoc gui trong topic da co mapping.

## Cach hoat dong

### Messenger -> Telegram

1. Listener nhan event tu `fbchat-v2`.
2. Event duoc parse thanh `IncomingMessengerMessage` hoac `IncomingMessengerActivity`.
3. Bridge tim topic da map theo `transport + messenger_id`.
4. Neu chua co topic, bot tao forum topic moi.
5. Tin nhan/activity duoc gui vao topic, co reply vao message Telegram goc neu co mapping.

### Telegram -> Messenger

1. Nguoi dung gui tin trong topic Telegram da map.
2. Bridge lay mapping topic de biet thread/chat JID Messenger dich.
3. Neu message la text/caption, bridge gui text sang Messenger.
4. Neu message la sticker, bridge tai file sticker tu Telegram va gui sang Messenger best-effort.
5. Message ID Messenger tra ve se duoc luu de reply va reaction/activity sau nay bam dung tin.

## Ho tro hien tai

| Chuc nang | Trang thai |
|---|---|
| Messenger text -> Telegram | Ho tro |
| Telegram text -> Messenger | Ho tro |
| Messenger reply -> Telegram reply | Ho tro neu co message ID mapping |
| Telegram reply -> Messenger reply | Ho tro neu co message ID mapping |
| Messenger reaction/activity -> Telegram | Ho tro |
| Telegram sticker -> Messenger | Ho tro best-effort |
| Messenger attachment -> Telegram | Hien link/mo ta neu event co URL |
| Telegram photo/video/file -> Messenger | Chua phai luong chinh, hien marker text neu khong phai sticker |
| E2EE text | Ho tro |
| E2EE sticker/media send | Ho tro qua binary da expose RPC media |

## Du lieu luu tru

Mac dinh du lieu runtime nam trong:

```text
data/bridge-store.json
```

File nay chua:

- Mapping Telegram topic -> Messenger conversation.
- Mapping Messenger message ID -> Telegram message ID.
- Quote data de gui reply va route reaction/edit/unsend.

Khong nen xoa file nay khi bridge dang chay. Neu xoa, bot van chay nhung se mat mapping cu va co the tao topic moi cho cac hoi thoai da tung map.

## Van hanh va bao mat

- Khong commit `.env`, cookie Facebook, `data/` hoac E2EE device/key file.
- Nen dung tai khoan phu de bridge vi Facebook/Messenger co the checkpoint session khi dung API khong chinh thuc.
- Cookie Facebook het han hoac bi checkpoint se lam listener/send that bai; khi do dang nhap lai Facebook va cap nhat cookie.
- Telegram topic ID co the stale neu topic bi xoa/dong; bridge co co che tao topic moi va retry.
- Telegram network co the timeout tam thoi; bridge da retry `TimedOut`, `NetworkError` va `RetryAfter`.
- Typing/read receipt co tan suat rat cao, nen mac dinh khong forward sang Telegram. Reaction, edit va unsend van duoc forward.
- E2EE phu thuoc binary Go cua `fbchat-v2`; neu binary cu, cac RPC sticker/media co the bao `unknown method`.

## Troubleshooting

### `Missing required environment variable: TG_TOKEN`

Kiem tra `.env` da ton tai trong thu muc `Messenger-Bridge-Telegram` va da dien `TG_TOKEN`.

### `TG_GROUP_ID` sai hoac bot khong phan hoi

Dam bao group ID co dang `-100...`, bot da duoc them vao dung group, va bot co quyen gui tin nhan.

### Bot khong tao topic moi

Chay `/checktopics`. Group phai la supergroup, da bat Topics, bot phai la admin va co quyen Manage Topics.

### `Could not import fbchat-v2 internal modules`

Set `FBCHAT_V2_SRC_PATH` ve dung thu muc chua `_core` va `_messaging`, vi du:

```env
FBCHAT_V2_SRC_PATH=../fbchat-v2/src
```

### Khong tim thay `fbchat-bridge-e2ee.exe`

Build binary theo muc Build E2EE binary, sau do set:

```env
FBCHAT_E2EE_BIN=../fbchat-v2/build/fbchat-bridge-e2ee.exe
```

### Topic hien ID thay vi ten nguoi dung

Messenger E2EE khong phai luc nao cung tra ten nguoi gui ngay trong event. Bridge se co gang resolve ten tu snapshot/profile va rename topic khi co du lieu.

### Reaction/edit/unsend khong reply vao message goc

Activity chi reply duoc vao message goc neu message do da tung di qua bridge va con nam trong cache mapping. Tang `MESSAGE_CACHE_LIMIT` neu can giu mapping lau hon.

### Telegram sticker gui sang Messenger bi loi `unknown method`

Binary E2EE bridge dang cu. Rebuild `fbchat-v2/bridge-e2ee` va dam bao `FBCHAT_E2EE_BIN` tro den binary moi.

## Kiem tra nhanh

Compile Python:

```powershell
cd "c:\Users\minhh\Downloads\mhwidev - project\Messenger-Bridge-Telegram"
python -m compileall src
```

Smoke test RPC sticker cua binary moi:

```powershell
cd "c:\Users\minhh\Downloads\mhwidev - project\fbchat-v2\bridge-e2ee"
'{"id":1,"method":"sendE2EESticker","params":{}}' | & "..\build\fbchat-bridge-e2ee.exe"
```

Ket qua mong doi khi chua login la:

```json
{"id":1,"ok":false,"error":"client not initialised"}
```

Neu ket qua la `unknown method`, binary chua duoc rebuild.

## Gioi han

- Day la bridge dua tren API/behavior khong chinh thuc cua Facebook Messenger, nen co the thay doi theo thoi gian.
- Media Messenger -> Telegram hien uu tien link/mo ta tu event, chua download/reupload day du moi loai attachment.
- Animated Telegram sticker `.tgs` khong phai dinh dang sticker native cua Messenger, nen duoc gui best-effort nhu file.
- E2EE can bridge Go va session/key hop le; lan dau ket noi co the can thoi gian khoi tao.
