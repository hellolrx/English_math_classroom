# English Math Classroom

以英文教授數學，讓香港中學生在英語環境中練習數學。  
Teach mathematics in English and collect class-level answer statistics.

## 快速開始｜Quick start

網站｜Web app: <https://english-math-classroom.pages.dev>

### 老師｜Teacher

1. 開啟網站，選擇「老師登入」。
2. 在「題目管理」選擇主題並上傳 `.xlsx` 檔案；系統會先預覽，確認後發布題庫。
3. 在「課堂／課後」選擇班級和題庫：
   - 課堂答題：建立課堂並展示 QR Code，學生掃描加入後開始答題。
   - 課後練習：建立練習碼，學生可使用練習碼進入。
4. 在「習題統計」選擇班級和題庫，查看自主練習及課堂答題的合併結果。
5. 在「單詞詞庫」按年級覆蓋上傳單詞，學生可按年級學習及複習。

### 學生｜Student

1. 在首頁選擇「學生登入」，使用學號和密碼登入。
2. 課堂答題：掃描老師展示的 QR Code，等待老師開始後作答。
3. 課後練習：輸入練習碼，或直接從題庫選擇主題練習。
4. 單詞模組：查看單詞和詞義後，選擇「忘記」「模糊」或「清楚記得」。

## Excel 格式｜Excel format

數學題目第一列使用以下欄位：

| 題目截圖 | 正確答案 | 來源 |
| --- | --- | --- |

- `題目截圖` 填入題目圖片。
- `正確答案` 填入 `A`、`B`、`C`、`D`；非選擇題可留空。
- `來源` 填入完整來源，例如 `DSE 2018 MT II (4)`。系統會自動提取年份、原題號和試卷部分。
- 同一主題再次上傳會覆蓋該主題的已發布題庫；學生既有作答記錄保留在原批次。

單詞檔案按目前單詞模板上傳；同一年級再次上傳會覆蓋該年級詞庫並重置該年級學習進度。

## Statistics

- 統計按班級和最新題庫查看。
- 課堂 QR Code、練習碼及學生直接進入題庫的作答會合併統計。
- 每道選擇題顯示 A-D 選項分布、提交人數及正確率。
- 非選擇題保留學生文字答案供老師查看，不進行自動判分。

## Development

```bash
cd frontend
npm install
npm run dev
```

後端部署設定位於 `backend/wrangler.jsonc`；前端部署至 Cloudflare Pages，後端使用 Cloudflare Workers。

## English summary

Teachers upload image-based math questions, publish a topic, and run a live classroom or after-class practice. Students sign in with their student number, join by QR code or practice code, and answer on their phones. Teachers review merged class-level answer distributions and accuracy. A separate vocabulary module supports spaced review with three self-assessment ratings.
