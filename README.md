# Screenshot to Corporate Comic Slides

將一組有順序的簡報截圖、照片或掃描頁，重製成品牌化的 16:9 企業漫畫／向量資訊圖簡報。流程會逐頁辨識內容、把簡體中文轉為臺灣繁體中文、將低解析截圖與現場照片改繪成一致的企業插畫，並在每一頁套用公司 LOGO，最後輸出 Slides 資源與 PPTX。

## 這個技能解決什麼問題

原始素材通常是手機翻拍或螢幕截圖：文字模糊、比例不一、混雜簡體字，而且充滿制式文字框。直接貼上會顯得粗糙。這個技能把每一頁重新設計成以視覺為主的企業資訊圖，同時保留原頁的資料、流程方向、設備與照片圖說。

## 環境需求

| 項目 | 需求 |
| --- | --- |
| Python | 3.10 以上 |
| 必裝套件 | `pillow`、`python-pptx`、`openai` |
| 驗證工具 | `pyyaml`（僅技能結構驗證時需要） |
| Manus 環境 | Slides MCP 與內建 LLM 代理（`OPENAI_API_KEY`、`OPENAI_API_BASE`） |

```bash
pip install pillow python-pptx openai pyyaml
```

## 安裝方式

### 方式一：直接複製技能資料夾

```bash
git clone https://github.com/k5801kaohom-blip/screenshot-to-comic-slides.git
cp -R screenshot-to-comic-slides/screenshot-to-comic-slides ~/skills/
```

### 方式二：使用安裝腳本

```bash
git clone https://github.com/k5801kaohom-blip/screenshot-to-comic-slides.git
cd screenshot-to-comic-slides
./install.sh
```

安裝腳本預設複製到 `~/skills/screenshot-to-comic-slides`，可用環境變數 `SKILLS_DIR` 指定其他位置。

### 方式三：打包成單一壓縮檔分享

```bash
./package.sh
# 產出 dist/screenshot-to-comic-slides-skill.zip
```

## 目錄結構

```
screenshot-to-comic-slides/
├── SKILL.md                            # 技能主文件與完整製作流程
├── references/
│   └── prompt-blueprints.md            # 首頁、架構圖、產品頁、案例頁與重修提示詞
├── scripts/
│   ├── make_contact_sheet.py           # 依序建立縮圖索引，確認頁序與完整性
│   ├── extract_slide_content.py        # 批次 OCR、語意抽取與臺灣繁體中文在地化
│   ├── locate_titles.py                # 全頁標題初定位
│   ├── refine_titles.py                # 裁切放大後取得精確標題框
│   ├── overlay_editable_titles.py      # 清除原標題並重建可編輯文字方塊
│   └── pack_image_slides_to_pptx.py    # 匯出逾時時的 PPTX 備援封裝
└── templates/
    ├── brand_brief.example.json        # 品牌色、LOGO 位置、術語對照範本
    └── title_overrides.example.json    # 標題覆寫設定範例
```

## 使用流程

1. 整理素材順序，建立 manifest（`slide_number`、`source_path`、`title_hint`）。
2. 用 `make_contact_sheet.py` 產生縮圖索引，確認沒有缺頁或重複。
3. 用 `extract_slide_content.py` 抽出每頁標題、重點、圖說與流程關係。
4. 依 `SKILL.md` 建立 Slides 圖像式簡報，第一頁單獨生成以鎖定畫風。
5. 其餘頁面以第一頁為風格參考、原截圖為內容參考批次生成。
6. 產生縮圖索引逐頁檢查：頁序、繁體字、術語、數據、LOGO、圖文對應。
7. 通過檢查後發佈 Slides 資源，並匯出 PPTX 交付。

### 指令範例

```bash
# 1) 縮圖索引
python scripts/make_contact_sheet.py manifest.json review/contact

# 2) 內容抽取（輸出每頁 JSON 與 summary.json）
python scripts/extract_slide_content.py manifest.json extraction --workers 4

# 3) PPTX 備援封裝
python scripts/pack_image_slides_to_pptx.py \
  generated deck.pptx --pattern 'slide_*' --expected-count 44
```

## 品牌與術語規範

品牌設定放在 `templates/brand_brief.example.json`，複製一份改成團隊自己的版本即可。預設值為 KAOHOM：

| 用途 | 色碼 |
| --- | --- |
| 深海軍藍 | `#0B2136` |
| KAOHOM 藍 | `#0052CC` |
| 青藍 | `#00B8D9` |
| 琥珀強調 | `#FFAB00` |

在地化用語對照（簡體 → 臺灣繁體）：

| 原用語 | 臺灣用語 |
| --- | --- |
| 基站 | 基地台 |
| 算法 | 演算法 |
| 接口 | 介面 |
| 實時 | 即時 |
| 米 | 公尺（長度單位時） |


## 可編輯大標模式（插圖保留、標題可改）

當需求是「插圖都保留，但大標要能自己改」時，走這條路線。插圖完全不動，只把烘焙在圖裡的標題換成真正的 PowerPoint 文字方塊。

```bash
# 1) 全頁標題初定位
python scripts/locate_titles.py generated title_bbox.json --workers 4

# 2) 裁切放大後取得精確標題框
python scripts/refine_titles.py generated title_bbox.json title_bbox_refined.json --workers 3

# 3) 建立可編輯標題版 PPTX
python scripts/overlay_editable_titles.py \
  --image-dir generated \
  --title-json title_bbox_refined.json \
  --overrides title_overrides.json \
  --out-dir out \
  --pptx deck_editable_titles.pptx \
  --report report.json \
  --image-format jpeg --jpeg-quality 90
```

`title_overrides.json` 以頁碼為鍵，只寫要改的頁面：

```json
{
  "1": { "skip": true },
  "24": { "title": "警察辦案區管理" },
  "30": { "title": "XXX 智慧醫院案例" },
  "42": { "title": "外企實驗室資產管控案例" }
}
```

- `skip: true` 用於純插圖頁（例如只有 LOGO 的封面）。
- 替換文字若與原稿行數相同，會保持原本的行數配置；行數不同時會依原稿行長重新分配。
- 清除原標題採用背景內插比對，因此深底白字與低對比標題都能一併處理。
- `--image-format jpeg --jpeg-quality 90` 可將檔案從約 90 MB 降到約 28 MB。

交付時請說明：大標與副標是可編輯文字，插圖內的標籤仍是圖像的一部分。

## 品質檢查重點

每一頁都要確認：頁序與原稿一致、LOGO 位置與比例正確、沒有簡體字或亂碼、技術數據與箭頭方向未被更動、插圖與原照片內容對應、不是以文字框拼排的頁面。未通過的頁面只需針對該頁重新生成，不必重跑整份簡報。

## 注意事項

圖像式簡報的頁面文字是插圖的一部分，無法像 PowerPoint 文字方塊逐字編輯。若需求是「每一個標籤都必須可編輯」，請改用 HTML／PPTX 版型路線，並先產生插圖素材再進 Slides 原生檔案編輯流程。
