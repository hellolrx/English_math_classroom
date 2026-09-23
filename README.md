# English Math Classroom

以英文教授數學，讓香港中學生在英語環境中練習數學。  
Teach mathematics in English and collect class-level answer statistics.

## 快速開始｜Quick start

網站｜Web app: <https://english-math-classroom.pages.dev>

### 老師｜Teacher

1. 開啟網站，選擇「老師登入」。
2. 測試帳戶：`admin` ／ `admin123`。
3. 進入「題目管理」，上傳 `.xlsx` 題目檔案。
4. 選擇檔案後系統會自動預覽，確認無誤後按「確認匯入」。
5. 開啟已建立的題目集合，按「去工作台建立課堂」。
6. 選擇「課堂答題」或「課後練習」：
   - 課堂答題：建立課堂並展示 QR Code，學生掃描後加入。
   - 課後練習：建立練習碼，將練習碼分享給學生。
7. 課堂完成後，進入「習題統計」查看即時課堂或課後練習的作答分布與正確率。

> 上線後請立即更改預設老師帳戶及密碼。  
> Change the default teacher credentials before production use.

### 學生｜Student

1. 在首頁選擇「學生入口」。
2. 課堂答題：掃描老師展示的 QR Code。
3. 課後練習：輸入老師提供的練習碼，系統會直接進入答題。
4. 選擇答案後按「下一題」，完成所有題目即可提交。

## Excel 格式｜Excel format

第一列使用以下欄位：

| 題目 | 選項A | 選項B | 選項C | 選項D | 正確答案 | 解析（可選） |
| --- | --- | --- | --- | --- | --- | --- |

- `正確答案` 可填 `A`、`B`、`C`、`D`，或 `1`、`2`、`3`、`4`。
- 題目和選項可使用文字或圖片；圖片會在匯入時自動處理並限制大小。
- 可參考 [example.xlsx](./導入示例/example.xlsx) 和 [example_img.xlsx](./導入示例/example_img.xlsx)。

## Statistics

- 課堂統計按班級及題目顯示，不顯示學生姓名。
- 顯示各選項的提交數量、正確答案及正確率。
- 課後練習不使用即時輪詢，老師可稍後到「習題統計」查看結果。

## English summary

Teachers upload an Excel question set, create either a live classroom or an after-class practice, and share the QR code or practice code with students. Students answer on their phones. Teachers can review answer distributions and accuracy by class without collecting student names.
