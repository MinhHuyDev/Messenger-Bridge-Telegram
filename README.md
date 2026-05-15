# Messenger Bridge Telegram

Messenger Bridge Telegram là công cụ bridge hai chiều giữa Facebook Messenger và Telegram Forum Topics. Dự án được viết bằng Python, sử dụng `fbchat-v2` để lắng nghe/gửi tin nhắn Messenger, bao gồm E2EE, và sử dụng `python-telegram-bot` để vận hành bot Telegram.

Mỗi hội thoại Messenger, gồm nhóm và chat 1-1, được ánh xạ vào một topic riêng trong Telegram supergroup. Tin nhắn, reply, reaction và các hoạt động realtime quan trọng sẽ được đưa vào đúng topic để có thể theo dõi tập trung trong một group Telegram.

## Tính năng chính

- Bridge hai chiều Messenger <-> Telegram.
- Tự động tạo Telegram forum topic cho hội thoại Messenger mới.
- Hỗ trợ Messenger thường và Messenger E2EE thông qua `fbchat-v2`.
- Chuyển tin nhắn Messenger sang Telegram, kèm mapping để reply đúng tin nhắn gốc khi có message ID.
- Chuyển tin nhắn Telegram trong topic đã ánh xạ ngược về Messenger.
- Hiển thị activity realtime của Messenger: reaction, gỡ reaction, edit message, unsend, typing, read receipt và E2EE receipt.
- Mặc định tắt typing/read receipt để tránh spam Telegram; có thể bật lại bằng biến môi trường.
- Gửi Telegram sticker sang Messenger theo khả năng transport: static sticker gửi như sticker/image, video/animated sticker gửi best-effort như video/file.
- Lưu mapping topic/message trong `data/bridge-store.json` để reply, reaction, edit và unsend có thể bám đúng tin gốc.
- Tự phục hồi khi Telegram topic bị xoá/đóng hoặc mapping topic bị stale.

## Kiến trúc

```text
Facebook Messenger
  -> fbchat-v2 listener / E2EE bridge
  -> src/messenger/client.py
  -> src/bridge.py
  -> python-telegram-bot
  -> Telegram supergroup forum topics
```

Các thành phần chính:

| File | Vai trò |
|---|---|
| `src/main.py` | Điểm khởi chạy, load cấu hình và chạy Telegram polling. |
| `src/config.py` | Đọc `.env`, auto-detect `fbchat-v2/src` và E2EE binary local. |
| `src/messenger/client.py` | Đăng nhập Messenger, lắng nghe E2EE/regular, gửi text/sticker/media best-effort. |
| `src/messenger/events.py` | Chuẩn hoá event thô của Messenger thành model tin nhắn/activity. |
| `src/bridge.py` | Điều phối hai chiều, tạo topic, recover topic, retry lỗi mạng Telegram. |
| `src/store.py` | Lưu mapping topic, message ID và quote data. |
| `src/tg/handlers.py` | Lệnh Telegram và message handler. |
| `src/utils/formatting.py` | Format HTML message/activity để gửi sang Telegram. |

## Yêu cầu

- Windows, Linux hoặc macOS.
- Python 3.10 trở lên. Dự án đã được chạy với Python 3.13.
- Telegram bot token từ BotFather.
- Telegram supergroup đã bật Topics.
- Bot Telegram phải là admin và có quyền Manage Topics.
- Cookie Facebook của tài khoản Messenger dùng để bridge.
- `fbchat-v2` và binary `fbchat-bridge-e2ee.exe` nếu cần Messenger E2EE.
- Go 1.24 trở lên nếu cần rebuild E2EE bridge binary.

## Cài đặt nhanh

Trong PowerShell:

```powershell
cd "c:\Users\minhh\Downloads\mhwidev - project\Messenger-Bridge-Telegram"
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env
```

Mở `.env` và điền các giá trị bắt buộc:

```env
TG_TOKEN=1234567890:replace_me
TG_GROUP_ID=-1001234567890
FACEBOOK_COOKIE=c_user=...; xs=...; fr=...; datr=...;
DATA_DIR=./data
```

Nếu dùng `fbchat-v2` local nằm cạnh thư mục project, chương trình thường tự detect được. Khi cần khai báo thủ công:

```env
FBCHAT_V2_SRC_PATH=../fbchat-v2/src
FBCHAT_E2EE_BIN=../fbchat-v2/build/fbchat-bridge-e2ee.exe
```

## Cấu hình `.env`

| Biến | Bắt buộc | Mô tả |
|---|---:|---|
| `TG_TOKEN` | Có | Token bot Telegram lấy từ BotFather. |
| `TG_GROUP_ID` | Có | ID Telegram supergroup, thường có dạng `-100...`. |
| `FACEBOOK_COOKIE` | Có* | Cookie Facebook của tài khoản Messenger. |
| `FACEBOOK_COOKIE_FILE` | Có* | Đường dẫn file chứa cookie, dùng thay cho `FACEBOOK_COOKIE`. |
| `DATA_DIR` | Không | Thư mục lưu `bridge-store.json`, mặc định là `./data`. |
| `FBCHAT_V2_SRC_PATH` | Không | Đường dẫn tới thư mục `fbchat-v2/src`. Project có auto-detect một số vị trí local. |
| `FBCHAT_E2EE_BIN` | Không | Đường dẫn tới binary `fbchat-bridge-e2ee.exe`. |
| `FBCHAT_ENABLE_E2EE` | Không | Bật/tắt E2EE listener, mặc định `1`. |
| `FBCHAT_E2EE_MEMORY_ONLY` | Không | Lưu key E2EE trong RAM, mặc định `1`. |
| `FBCHAT_E2EE_DEVICE_PATH` | Không | File persist device/key E2EE khi không dùng memory-only. |
| `FBCHAT_E2EE_LOG_LEVEL` | Không | Log level của bridge E2EE, mặc định `none`. |
| `FBCHAT_E2EE_SEND_TIMEOUT` | Không | Timeout cho send E2EE RPC, mặc định `180` giây. |
| `IGNORE_SELF_MESSAGES` | Không | Bỏ qua tin do chính tài khoản Facebook gửi, mặc định `1`. |
| `MESSAGE_CACHE_LIMIT` | Không | Số mapping message giữ lại để reply/activity, mặc định `3000`. |
| `TG_CONNECT_TIMEOUT` | Không | Timeout kết nối Telegram Bot API, mặc định `15`. |
| `TG_READ_TIMEOUT` | Không | Timeout đọc response Telegram Bot API, mặc định `45`. |
| `TG_WRITE_TIMEOUT` | Không | Timeout gửi request Telegram Bot API, mặc định `45`. |
| `TG_POOL_TIMEOUT` | Không | Timeout chờ connection pool Telegram, mặc định `30`. |
| `FORWARD_TYPING_ACTIVITY` | Không | Forward typing indicator sang Telegram. Mặc định `0` để tránh spam. |
| `FORWARD_READ_RECEIPTS` | Không | Forward read receipt sang Telegram. Mặc định `0` để tránh spam. |

`FACEBOOK_COOKIE` và `FACEBOOK_COOKIE_FILE` là hai cách thay thế nhau; chỉ cần dùng một trong hai.

## Chuẩn bị Telegram group

1. Tạo bot bằng BotFather và copy token vào `TG_TOKEN`.
2. Tạo Telegram group, convert thành supergroup nếu cần.
3. Bật Topics trong group settings.
4. Thêm bot vào group.
5. Promote bot thành admin.
6. Bật quyền Manage Topics và quyền gửi tin nhắn.
7. Lấy group ID dạng `-100...` và điền vào `TG_GROUP_ID`.

Sau khi chạy bot, dùng lệnh `/checktopics` trong group để kiểm tra quyền tạo topic.

## Build E2EE binary

Nếu đã có `fbchat-v2/build/fbchat-bridge-e2ee.exe`, có thể bỏ qua bước này. Nếu chưa có hoặc vừa sửa RPC media/sticker, rebuild binary:

```powershell
cd "c:\Users\minhh\Downloads\mhwidev - project\fbchat-v2\bridge-e2ee"
go mod tidy
go build -ldflags="-s -w" -o ..\build\fbchat-bridge-e2ee.exe .
```

Sau đó đảm bảo `.env` trỏ đúng binary:

```env
FBCHAT_E2EE_BIN=../fbchat-v2/build/fbchat-bridge-e2ee.exe
```

## Chạy bridge

```powershell
cd "c:\Users\minhh\Downloads\mhwidev - project\Messenger-Bridge-Telegram"
.\.venv\Scripts\Activate.ps1
python .\src\main.py
```

Khi bridge khởi động thành công, bot sẽ gửi thông báo vào Telegram group. Khi có hội thoại Messenger mới, bridge sẽ tạo topic mới và bắt đầu forward tin nhắn/activity vào topic đó.

## Lệnh Telegram

| Lệnh | Mô tả |
|---|---|
| `/help` | Hiển thị hướng dẫn sử dụng cơ bản. |
| `/status` | Xem trạng thái listener, Facebook ID và số topic đã map. |
| `/checktopics` | Kiểm tra supergroup, Topics và quyền Manage Topics của bot. |
| `/topic list` | Liệt kê các topic đã map với Messenger. |
| `/topic info` | Xem mapping của topic hiện tại. |
| `/topic delete` | Xoá mapping của topic hiện tại. |

Tin nhắn và sticker Telegram chỉ được forward về Messenger khi được gửi trong topic đã có mapping.

## Cách hoạt động

### Messenger sang Telegram

1. Listener nhận event từ `fbchat-v2`.
2. Event được parse thành `IncomingMessengerMessage` hoặc `IncomingMessengerActivity`.
3. Bridge tìm topic đã map theo `transport + messenger_id`.
4. Nếu chưa có topic, bot tạo forum topic mới.
5. Tin nhắn/activity được gửi vào topic, có reply vào message Telegram gốc nếu có mapping.

### Telegram sang Messenger

1. Người dùng gửi tin trong topic Telegram đã map.
2. Bridge lấy mapping topic để biết thread/chat JID Messenger đích.
3. Nếu message là text/caption, bridge gửi text sang Messenger.
4. Nếu message là sticker, bridge tải file sticker từ Telegram và gửi sang Messenger best-effort.
5. Message ID Messenger trả về sẽ được lưu lại để các reply, reaction và activity sau này có thể bám đúng tin.

## Trạng thái hỗ trợ

| Chức năng | Trạng thái |
|---|---|
| Messenger text sang Telegram | Hỗ trợ |
| Telegram text sang Messenger | Hỗ trợ |
| Messenger reply sang Telegram reply | Hỗ trợ nếu có message ID mapping |
| Telegram reply sang Messenger reply | Hỗ trợ nếu có message ID mapping |
| Messenger reaction/edit/unsend sang Telegram | Hỗ trợ |
| Messenger typing/read receipt sang Telegram | Có thể bật, mặc định tắt để tránh spam |
| Telegram sticker sang Messenger | Hỗ trợ best-effort |
| Messenger attachment sang Telegram | Hiển thị link/mô tả nếu event có URL |
| Telegram photo/video/file sang Messenger | Chưa phải luồng chính; hiện ưu tiên text/sticker |
| E2EE text | Hỗ trợ |
| Gửi E2EE sticker/media | Hỗ trợ qua binary đã expose RPC media |

## Dữ liệu lưu trữ

Dữ liệu runtime mặc định nằm trong:

```text
data/bridge-store.json
```

File này chứa:

- Mapping Telegram topic sang Messenger conversation.
- Mapping Messenger message ID sang Telegram message ID.
- Quote data để gửi reply và route reaction/edit/unsend.

Không nên xoá file này khi bridge đang chạy. Nếu xoá, bot vẫn chạy nhưng sẽ mất mapping cũ và có thể tạo topic mới cho các hội thoại đã từng map.

## Vận hành và bảo mật

- Không commit `.env`, cookie Facebook, thư mục `data/` hoặc file E2EE device/key.
- Nên dùng tài khoản phụ để bridge vì Facebook/Messenger có thể checkpoint session khi dùng API không chính thức.
- Cookie Facebook hết hạn hoặc bị checkpoint sẽ làm listener/send thất bại; khi đó cần đăng nhập lại Facebook và cập nhật cookie.
- Telegram topic ID có thể stale nếu topic bị xoá/đóng; bridge có cơ chế tạo topic mới và retry.
- Telegram network có thể timeout tạm thời; bridge đã retry `TimedOut`, `NetworkError` và `RetryAfter`.
- Typing/read receipt có tần suất rất cao, nên mặc định không forward sang Telegram. Reaction, edit và unsend vẫn được forward.
- E2EE phụ thuộc binary Go của `fbchat-v2`; nếu binary cũ, các RPC sticker/media có thể báo `unknown method`.

## Troubleshooting

### `Missing required environment variable: TG_TOKEN`

Kiểm tra `.env` đã tồn tại trong thư mục `Messenger-Bridge-Telegram` và đã điền `TG_TOKEN`.

### `TG_GROUP_ID` sai hoặc bot không phản hồi

Đảm bảo group ID có dạng `-100...`, bot đã được thêm vào đúng group và bot có quyền gửi tin nhắn.

### Bot không tạo topic mới

Chạy `/checktopics`. Group phải là supergroup, đã bật Topics, bot phải là admin và có quyền Manage Topics.

### `Could not import fbchat-v2 internal modules`

Set `FBCHAT_V2_SRC_PATH` về đúng thư mục chứa `_core` và `_messaging`, ví dụ:

```env
FBCHAT_V2_SRC_PATH=../fbchat-v2/src
```

### Không tìm thấy `fbchat-bridge-e2ee.exe`

Build binary theo mục Build E2EE binary, sau đó set:

```env
FBCHAT_E2EE_BIN=../fbchat-v2/build/fbchat-bridge-e2ee.exe
```

### Topic hiện ID thay vì tên người dùng

Messenger E2EE không phải lúc nào cũng trả tên người gửi ngay trong event. Bridge sẽ cố gắng resolve tên từ snapshot/profile và rename topic khi có dữ liệu.

### Reaction/edit/unsend không reply vào message gốc

Activity chỉ reply được vào message gốc nếu message đó đã từng đi qua bridge và còn nằm trong cache mapping. Tăng `MESSAGE_CACHE_LIMIT` nếu cần giữ mapping lâu hơn.

### E2EE reply báo `sendE2EEMessage timed out after 60.0s`

Cập nhật source mới và restart bot. Bridge hiện dùng `FBCHAT_E2EE_SEND_TIMEOUT`, mặc định `180` giây, đồng thời bỏ metadata reply E2EE nếu thiếu `senderJid` để tránh treo quoted message. Nếu vẫn timeout, Messenger E2EE session có thể đang bị nghẽn; restart bot để tạo lại bridge process.

### Telegram báo timeout liên tục khi `send_message`

Giữ `FORWARD_TYPING_ACTIVITY=0` và `FORWARD_READ_RECEIPTS=0` để tránh spam activity. Nếu mạng Telegram chậm, tăng `TG_READ_TIMEOUT`, `TG_WRITE_TIMEOUT` và `TG_POOL_TIMEOUT` trong `.env`.

### Telegram sticker gửi sang Messenger báo `unknown method`

Binary E2EE bridge đang cũ. Rebuild `fbchat-v2/bridge-e2ee` và đảm bảo `FBCHAT_E2EE_BIN` trỏ đến binary mới.

## Kiểm tra nhanh

Compile Python:

```powershell
cd "c:\Users\minhh\Downloads\mhwidev - project\Messenger-Bridge-Telegram"
python -m compileall src
```

Smoke test RPC sticker của binary mới:

```powershell
cd "c:\Users\minhh\Downloads\mhwidev - project\fbchat-v2\bridge-e2ee"
'{"id":1,"method":"sendE2EESticker","params":{}}' | & "..\build\fbchat-bridge-e2ee.exe"
```

Kết quả mong đợi khi chưa login là:

```json
{"id":1,"ok":false,"error":"client not initialised"}
```

Nếu kết quả là `unknown method`, binary chưa được rebuild.

## Giới hạn hiện tại

- Bridge dựa trên API/behavior không chính thức của Facebook Messenger, nên có thể thay đổi theo thời gian.
- Media Messenger sang Telegram hiện ưu tiên link/mô tả từ event, chưa download/reupload đầy đủ mọi loại attachment.
- Animated Telegram sticker `.tgs` không phải định dạng sticker native của Messenger, nên được gửi best-effort như file.
- E2EE cần bridge Go và session/key hợp lệ; lần đầu kết nối có thể cần thời gian khởi tạo.
