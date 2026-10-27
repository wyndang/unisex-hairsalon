# unisex-hairsalon
Cài đặt tất cả thư viện:
pip install -r requirements.txt
Pull và chạy backend:

git clone https://github.com/wyndang/unisex-hairsalon.git
cd unisex-hairsalon/backend
python3 -m venv venv
source venv/bin/activate 
uvicorn main:app --reload --port 8000
http://localhost:8000/docs

Frontend:
cd unisex-hairsalon/frontend
python3 -m http.server 5500
git pull origin main

