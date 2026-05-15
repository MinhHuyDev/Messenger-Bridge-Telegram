# Messenger Bridge Telegram

Bridge hai chieu giua Facebook Messenger va Telegram Forum Topics, viet bang Python.
Du an nay bam theo y tuong cua `zalo-tg`: moi hoi thoai Messenger duoc gan voi mot topic Telegram rieng, co store de luu mapping topic va mapping reply.

## Tinh nang

- Lang nghe Messenger bang `fbchat-v2` E2EE listener: `_messaging._listening_e2ee.listeningE2EEEvent`.
- Gui Messenger E2EE bang `_messaging._send_e2ee.api(listener=...)`, tai su dung bridge process cua listener.
- Tu dong tao Telegram forum topic cho moi hoi thoai Messenger moi.
- Chuyen tin nhan Messenger sang Telegram va tin nhan Telegram trong topic nguoc ve Messenger.
- Hien realtime cac activity cua Messenger vao dung topic: reaction, go reaction, edit, unsend, typing, read receipt va E2EE receipt.
- Gui Telegram sticker nguoc sang Messenger: static sticker di nhu sticker/image, video/animated sticker di nhu file/video tuy transport.
- Luu mapping topic va message reply trong `data/bridge-store.json`.
- Ho tro E2EE DM va regular Messenger event ma bridge Go tra ve. Media Messenger den Telegram hien duoc forward duoi dang link/mo ta neu event co URL.

## Cai dat

```powershell
cd "c:\Users\minhh\Downloads\mhwidev - project\Messenger-Bridge-Telegram"
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
```

Sua `.env`:

- `TG_TOKEN`: token bot Telegram.
- `TG_GROUP_ID`: id supergroup da bat Topics.
- `FACEBOOK_COOKIE` hoac `FACEBOOK_COOKIE_FILE`: cookie Facebook cua tai khoan Messenger.
- `FBCHAT_E2EE_BIN`: duong dan toi binary `fbchat-bridge-e2ee.exe` neu PyPI chua co san binary.

Neu dung source `fbchat-v2` local trong workspace nay, co the dat:

```env
FBCHAT_V2_SRC_PATH=../fbchat-v2/src
FBCHAT_E2EE_BIN=../fbchat-v2/build/fbchat-bridge-e2ee.exe
```

## Build E2EE binary cua fbchat-v2

Neu chua co `fbchat-bridge-e2ee.exe`:

```powershell
cd "c:\Users\minhh\Downloads\mhwidev - project\fbchat-v2\bridge-e2ee"
go mod tidy
go build -ldflags="-s -w" -o ..\build\fbchat-bridge-e2ee.exe .
```

Sau do tro `FBCHAT_E2EE_BIN` trong `.env` ve file vua build.

## Chay

```powershell
cd "c:\Users\minhh\Downloads\mhwidev - project\Messenger-Bridge-Telegram"
.\.venv\Scripts\Activate.ps1
python .\src\main.py
```

Khi co tin nhan Messenger den, bot se tao topic Telegram moi va forward tin vao do. Gui tin nhan trong topic da map de forward nguoc ve Messenger.

## Lenh Telegram

- `/status`: xem trang thai listener, Facebook ID va so topic.
- `/checktopics`: kiem tra group co bat Topics va bot co quyen tao topic khong.
- `/topic list`: liet ke topic da map.
- `/topic info`: xem mapping cua topic hien tai.
- `/topic delete`: xoa mapping cua topic hien tai.

## Ghi chu van hanh

- Bot Telegram can quyen admin `Manage Topics` de tu tao topic.
- Cookie Facebook co rui ro bao mat; chi luu tren may ban tin tuong va khong commit `.env`.
- E2EE Messenger phu thuoc bridge Go cua `fbchat-v2`; neu listener bao loi khong tim thay binary, build binary va set `FBCHAT_E2EE_BIN`.
- Attachment E2EE tu Messenger duoc hien thanh link/mo ta neu event co URL. Telegram sticker can binary `fbchat-bridge-e2ee.exe` da rebuild voi cac RPC media moi.
# Zalo Bridge Messenger

Du an nay la bridge hai chieu giua Zalo va Facebook Messenger, duoc dung theo kien truc cua `zalo-tg` va adapter Messenger dua tren thu vien `fbchat-v2`.

Thu muc `Messenger-Bridge-Telegram` chua toan bo ma nguon can thiet cho bridge:

```text
Messenger-Bridge-Telegram/
├── .env.example
├── .gitignore
├── package.json              # phu thuoc Node cho Zalo worker
├── requirements.txt          # phu thuoc Python va fbchat-v2
├── routes.example.json       # mau anh xa hoi thoai
└── src/
		├── main.py               # entrypoint
		├── zalo_worker.js        # worker Node dung zca-js
		└── bridge/               # orchestrator Python
```

## Kien truc

Bridge chay mot tien trinh Python lam trung tam dieu phoi:

```text
Zalo WebSocket API
	-> src/zalo_worker.js      # zca-js, QR login, listen/send
	-> JSONL over stdin/stdout
	-> src/bridge/app.py       # route, dedupe, echo guard, media best-effort
	-> fbchat-v2               # send Messenger + GraphQL polling listener
	-> Messenger Web
```

Ly do tach Zalo thanh worker Node: `zalo-tg` da dung `zca-js` on dinh cho Zalo, trong khi `fbchat-v2` la Python. JSONL giu hai ben doc lap va de debug.

## Tinh nang

- Dong bo tin nhan van ban Zalo -> Messenger va Messenger -> Zalo.
- Ho tro route nhieu cap hoi thoai bang `routes.json`.
- Ho tro DM va group Zalo, DM va thread/group Messenger.
- Chuyen tiep tep/anh/video theo co che best-effort:
	- Zalo media URL -> tai tam -> upload Messenger.
	- Messenger attachment preview URL -> tai tam -> upload Zalo.
- Chong echo bang cache message ID va conversation dang gui.
- Dang nhap Zalo bang QR neu chua co credentials.
- Dung cookie Facebook cua `fbchat-v2`; mac dinh nhan tin bang `polling` de tranh loi sync queue cua MQTT cu.

## Cai dat

Yeu cau:

- Python 3.10 tro len.
- Node.js 18 tro len.
- Thu muc `fbchat-v2` nam canh thu muc nay, hoac khai bao `FBCHAT_SRC` trong `.env`.

Trong PowerShell:

```powershell
cd "c:\Users\minhh\Downloads\mhwidev - project\Messenger-Bridge-Telegram"
python -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements.txt
npm install
Copy-Item .env.example .env
New-Item -ItemType Directory -Force data
Copy-Item routes.example.json data\routes.json
```

## Cau hinh

Mo `.env` va dien cac gia tri quan trong:

```env
FACEBOOK_COOKIE=c_user=...; xs=...; fr=...;
FBCHAT_SRC=../fbchat-v2/src
FACEBOOK_LISTENER=polling
DATA_DIR=./data
ROUTES_PATH=./data/routes.json
ZALO_CREDENTIALS_PATH=./data/zalo-credentials.json
```

Mo `data/routes.json` va them cac cap hoi thoai can bridge:

```json
{
	"routes": [
		{
			"name": "demo-dm",
			"enabled": true,
			"zalo": { "id": "ZALO_UID", "type": "user" },
			"messenger": { "id": "FACEBOOK_UID", "type": "user" }
		},
		{
			"name": "demo-group",
			"enabled": true,
			"zalo": { "id": "ZALO_GROUP_ID", "type": "group" },
			"messenger": { "id": "FACEBOOK_THREAD_ID", "type": "thread" }
		}
	]
}
```

Kieu hop le:

| Ben | `type` | Ghi chu |
|---|---|---|
| Zalo | `user` | chat 1-1, `id` la UID Zalo |
| Zalo | `group` | group Zalo, `id` la group ID |
| Messenger | `user` | chat 1-1, `id` la Facebook UID |
| Messenger | `thread` | nhom Messenger, `id` la thread FBID |

## Chay

```powershell
.\.venv\Scripts\python src\main.py
```

Lan dau chay, neu chua co `data/zalo-credentials.json`, terminal se hien QR Zalo. Mo app Zalo tren dien thoai va quet QR de luu phien dang nhap.

Neu QR trong terminal kho quet, hay mo file anh `.png` duoc log o dong `QR image ready: ...` va quet anh do. QR het han rat nhanh; neu thay `Zalo QR expired`, hay quet ma moi vua duoc tao.

## Ghi chu bao mat

- Khong commit `.env`, `data/`, cookie Facebook hoac credentials Zalo.
- Day la API khong chinh thuc, nen dung tai khoan phu va chap nhan rui ro checkpoint/session het han.
- Tin nhan duoc chuyen qua hai nen tang bang tai khoan nguoi dung that, hay kiem tra route truoc khi chay lau dai.

## Debug nhanh

Kiem tra Python:

```powershell
.\.venv\Scripts\python -m py_compile src\main.py src\bridge\*.py
```

Kiem tra worker Node:

```powershell
node --check src\zalo_worker.js
```

### Loi `ERROR_QUEUE_OVERFLOW` cua Messenger

Neu log co dang:

```text
Publishing to /messenger_sync_create_queue with seq_id: None
ERR ERROR_QUEUE_OVERFLOW
```

nghia la listener MQTT cu cua Messenger khong tao duoc sync queue. Hay dung `FACEBOOK_LISTENER=polling` trong `.env` de bridge doc tin moi qua GraphQL thread list. Neu polling cung bao loi `fb_dtsg` hoac `last_seq_id`, hay dang nhap lai `facebook.com`, copy cookie moi vao `FACEBOOK_COOKIE`, roi chay lai bridge.
