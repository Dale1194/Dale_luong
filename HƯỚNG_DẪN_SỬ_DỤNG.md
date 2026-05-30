# 📖 Hướng dẫn sử dụng - Tự học tiếng Trung

## 1. Cài đặt và khởi chạy

### Chạy từ mã nguồn
```
python App.py
```

### Chạy từ file EXE
Mở file `TuHocTiengTrung.exe` trong thư mục `dist/` sau khi build.

### Build thành EXE
```
build_exe.bat
```

---

## 2. Chuẩn bị file Excel từ vựng

File Excel `.xlsx` cần có các cột theo thứ tự:

| Cột A | Cột B | Cột C | Cột D | Cột E |
|-------|-------|-------|-------|-------|
| Chữ Hán | Pinyin | Nghĩa tiếng Việt | Chủ đề (tùy chọn) | Câu ví dụ (tùy chọn) |

**Ví dụ:**

| chữ Hán | pinyin | nghĩa tiếng Việt | chủ đề | câu ví dụ |
|---------|--------|-------------------|--------|-----------|
| 你好 | nǐ hǎo | xin chào | Chào hỏi | 你好，很高兴认识你 |
| 谢谢 | xiè xiè | cảm ơn | Chào hỏi | 谢谢你的帮助 |
| 学习 | xué xí | học tập | Học tập | 我喜欢学习中文 |

> **Lưu ý:** Hàng đầu tiên (tiêu đề) sẽ tự động bị bỏ qua nếu nhận dạng được.

---

## 3. Giao diện chính

### Thanh công cụ (trên cùng)
- **Mở file Excel** — Chọn file `.xlsx` từ vựng
- **File gần đây** — Mở nhanh các file đã dùng gần đây
- **Tiến độ từ** — Xem bảng tiến độ chi tiết từng từ
- **TK chủ đề** — Thống kê theo chủ đề (% thuộc, tổng đúng/sai)
- **Học tập trung** — Ẩn bảng lịch sử và dashboard, chỉ giữ phần học
- **Cài đặt** — Mở cửa sổ tùy chọn
- **About** — Thông tin ứng dụng
- **Ẩn/Hiện biểu đồ** — Bật/tắt biểu đồ 7 ngày

### Khu vực Bắt đầu nhanh
- **Kiểu phiên:** Ngẫu nhiên, Lặp lại ngắt quãng, Toàn bộ, 10 từ sai gần nhất, Từ hay quên
- **Chủ đề:** Lọc theo chủ đề trong file Excel
- **Bắt đầu phiên:** Bắt đầu phiên học mới

### Khu vực học (bên phải)
- Hiển thị từ cần học (chữ Hán hoặc nghĩa tùy chế độ)
- Ô nhập đáp án
- Các nút thao tác

### Các nút thao tác

| Nút | Phím tắt | Chức năng |
|-----|----------|-----------|
| Kiểm tra | `Enter` | Kiểm tra đáp án đã nhập |
| Phát âm | `Ctrl+P` | Phát âm từ hiện tại |
| Gợi ý | `Ctrl+H` | Hiện gợi ý (che bớt ký tự) |
| Bỏ qua | `Ctrl+S` | Bỏ qua, hiện đáp án |
| Tiếp theo | `Ctrl+N` | Chuyển sang từ tiếp theo |
| Làm lại | — | Làm lại toàn bộ phiên |
| Ôn từ sai | — | Ôn lại tất cả từ sai |
| Ôn 10 từ sai | — | Ôn nhanh 10 từ sai gần nhất |
| Xuất từ sai | — | Xuất danh sách từ sai ra file Excel |
| Xuất lịch sử | — | Xuất lịch sử học ra Excel/CSV |
| Xóa từ sai | — | Xóa toàn bộ danh sách từ sai |
| Xóa lịch sử | — | Xóa bảng lịch sử kiểm tra |
| Tạm dừng | — | Tạm dừng phiên học, nhớ vị trí |
| Tiếp tục | — | Tiếp tục phiên đã tạm dừng |
| Báo cáo sai | — | Mở bảng chi tiết tất cả từ sai trong phiên |
| Chế độ nghe | `Ctrl+L` | Mở chế độ luyện nghe |
| Tìm từ | `Ctrl+F` | Tìm và nhảy tới từ trong phiên |

---

## 4. Chế độ câu hỏi

Có 2 chế độ chính (chọn trong **Cài đặt**):

1. **Chế độ 1 — Hiển thị chữ Hán, điền nghĩa tiếng Việt**
   - Ứng dụng hiện chữ Hán → bạn nhập nghĩa tiếng Việt
   - Phù hợp cho người đang học đọc hiểu

2. **Chế độ 2 — Hiển thị nghĩa tiếng Việt, điền chữ Hán**
   - Ứng dụng hiện nghĩa → bạn nhập chữ Hán
   - Phù hợp cho người đang luyện viết

---

## 5. Kiểu phiên học

| Kiểu phiên | Mô tả |
|-------------|-------|
| **Ngẫu nhiên** | Chọn ngẫu nhiên từ toàn bộ danh sách (có thể giới hạn số lượng) |
| **Lặp lại ngắt quãng** | Ưu tiên từ đến hạn ôn tập theo thuật toán SM-2 |
| **Toàn bộ** | Học hết tất cả từ trong file |
| **10 từ sai gần nhất** | Ôn nhanh 10 từ sai gần nhất trong lịch sử |
| **Từ hay quên** | Ưu tiên từ có tỷ lệ sai cao, sai nhiều lần |

### Giới hạn số từ mỗi phiên
Trong ô "Khoảng số từ mỗi phiên":
- Đặt **0 và 0** → Học tất cả
- Đặt ví dụ **10 và 20** → Chọn ngẫu nhiên 10-20 từ mỗi phiên

---

## 6. Thuật toán ôn tập SM-2

Ứng dụng sử dụng thuật toán **SuperMemo 2 (SM-2)** để lên lịch ôn tập:

- **Trả lời đúng lần 1:** Ôn lại sau 1 ngày
- **Trả lời đúng lần 2:** Ôn lại sau 6 ngày
- **Từ lần 3 trở đi:** Khoảng cách ôn = lần trước × hệ số dễ (ease factor)
- **Trả lời sai:** Reset về 1 ngày, giảm hệ số dễ

Hệ số dễ (ease factor) tự điều chỉnh theo hiệu suất:
- Đúng không cần gợi ý → tăng ease factor
- Đúng có gợi ý → giữ nguyên hoặc tăng ít
- Sai → giảm ease factor (tối thiểu 1.3)

---

## 7. Chế độ nghe (`Ctrl+L`)

1. Mở chế độ nghe từ nút **Chế độ nghe** hoặc `Ctrl+L`
2. Ứng dụng phát âm từ → bạn nghe rồi nhập chữ Hán hoặc nghĩa
3. Bấm **Kiểm tra** (hoặc `Enter`) để xem kết quả
4. Bấm **Tiếp theo** (hoặc `Enter` lần nữa) để sang từ tiếp

> **Yêu cầu:** Cần cài giọng tiếng Trung trên Windows.
> Vào **Settings → Time & Language → Language → Add a language → 中文 (Simplified)** và đảm bảo tích chọn **Speech**.

---

## 8. Tìm từ nhanh (`Ctrl+F`)

1. Bấm `Ctrl+F` hoặc nút **Tìm từ**
2. Nhập từ khóa (chữ Hán, pinyin, hoặc nghĩa)
3. Kết quả xuất hiện theo thời gian thực
4. Double-click hoặc bấm **Nhảy tới từ** để chuyển tới từ đó trong phiên

---

## 9. Cài đặt

| Tùy chọn | Mô tả |
|-----------|-------|
| Hiện biểu đồ thống kê | Bật/tắt biểu đồ 7 ngày |
| Tự động chuyển từ tiếp | Tự chuyển từ sau 0.9 giây khi đúng |
| Hiện pinyin bên cạnh chữ Hán | Hiện pinyin nhỏ bên phải chữ Hán |
| Hiện pinyin trong gợi ý/đáp án | Bao gồm pinyin khi gợi ý hoặc xem đáp án |
| Hiệu ứng chuyển từ mới | Bật/tắt animation khi chuyển từ |
| Chế độ tối (Dark mode) | Giao diện tối bảo vệ mắt |
| Chế độ câu hỏi | Chọn Hán→Việt hoặc Việt→Hán |
| Giới hạn lịch sử | Số dòng lịch sử tối đa lưu lại |

---

## 10. Tạm dừng / Tiếp tục phiên

- **Tạm dừng:** Bấm nút **Tạm dừng** để dừng phiên, ghi nhớ vị trí hiện tại
- **Tiếp tục:** Bấm nút **Tiếp tục** để học tiếp từ vị trí đã dừng

---

## 11. Thống kê theo chủ đề

Bấm nút **TK chủ đề** trên thanh công cụ để xem:
- Tổng số từ mỗi chủ đề
- Số từ đã thuộc (mastery ≥ 4)
- Phần trăm thuộc
- Tổng số lần đúng/sai

→ Giúp xác định chủ đề yếu cần ôn thêm.

---

## 12. Báo cáo từ sai chi tiết

Khi kết thúc phiên hoặc bấm nút **Báo cáo sai**:
- Hiển thị bảng chi tiết **tất cả** từ sai trong phiên (không giới hạn 5 từ)
- Bao gồm: chữ Hán, pinyin, nghĩa, chủ đề, mức nhớ

---

## 13. Dark Mode (Chế độ tối)

- Bật trong **Cài đặt → Chế độ tối (Dark mode)**
- Toàn bộ giao diện chuyển sang tông tối
- Phù hợp khi học ban đêm, bảo vệ mắt
- Cài đặt được lưu lại khi đóng ứng dụng

---

## 14. Phím tắt tổng hợp

| Phím tắt | Chức năng |
|----------|-----------|
| `Enter` | Kiểm tra đáp án |
| `Ctrl+H` | Gợi ý |
| `Ctrl+S` | Bỏ qua từ |
| `Ctrl+N` | Từ tiếp theo |
| `Ctrl+P` | Phát âm |
| `Ctrl+F` | Tìm từ trong phiên |
| `Ctrl+L` | Mở chế độ nghe |

---

## 15. File dữ liệu

Ứng dụng tạo các file dữ liệu trong cùng thư mục:

| File | Nội dung |
|------|----------|
| `cài_đặt.json` | Lưu cài đặt người dùng |
| `lịch_sử_học.json` | Lịch sử kiểm tra (đúng/sai) |
| `tiến_độ_từ_vựng.json` | Tiến độ từng từ (SM-2 data) |

> Dữ liệu được tự động lưu mỗi 30 giây và khi đóng ứng dụng. Sử dụng ghi file an toàn (atomic write) để tránh mất dữ liệu.

---

## 16. Câu ví dụ trong Excel

Cột E (tùy chọn) chứa câu ví dụ cho từ vựng. Khi có, câu ví dụ sẽ hiển thị bên dưới thông tin từ trong quá trình học.

---

## 17. Lưu ý

- Ứng dụng chỉ hỗ trợ file `.xlsx` (Excel 2007+), không hỗ trợ `.xls`
- Phát âm yêu cầu Windows có cài giọng tiếng Trung
- Dữ liệu lịch sử và tiến độ nằm cạnh file `App.py` hoặc `TuHocTiengTrung.exe`
- Khi xuất file EXE, file `app.ico` cần có nhiều kích thước (16px đến 256px)

---

**Phiên bản:** 1.0.0
**Tác giả:** Lương Văn Đại - Dale_Luong
**Liên hệ:** DALE_LUONG@pegatroncorp.com - 0988.279.296
