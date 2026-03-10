import os
from datetime import datetime, timedelta
from jose import JWTError, jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from dotenv import load_dotenv

# โหลดค่าตัวแปรจากไฟล์ .env
load_dotenv()

# ⚙️ ดึงค่าตัวแปรสภาพแวดล้อม (ถ้าระบบหา .env ไม่เจอ จะใช้ค่า Default ด้านหลังแทน)
ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "admin")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "quantum2026")
SECRET_KEY = os.getenv("SECRET_KEY", "SUPER_SECRET_QUANTUM_KEY")
ALGORITHM = os.getenv("ALGORITHM", "HS256")
ACCESS_TOKEN_EXPIRE_DAYS = int(os.getenv("ACCESS_TOKEN_EXPIRE_DAYS", 7))

# กำหนด Endpoint ที่ Frontend จะต้องยิงมาเพื่อขอ Token
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="login")

def create_access_token(data: dict):
    """
    ฟังก์ชันสำหรับสร้าง JWT Token เมื่อ Admin ล็อกอินสำเร็จ
    """
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(days=ACCESS_TOKEN_EXPIRE_DAYS)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

def get_current_admin(token: str = Depends(oauth2_scheme)):
    """
    Middleware สำหรับตรวจสอบกุญแจ (Token) ทุกครั้งที่มีการเรียกใช้งาน API ที่เป็นความลับ
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="ไม่สามารถยืนยันตัวตนได้ หรือ Token หมดอายุ",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        # ถอดรหัส Token
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        
        # เช็คว่าคนที่ถือ Token คือ Admin ตัวจริงหรือไม่
        if username != ADMIN_USERNAME:
            raise credentials_exception
            
        return username
        
    except JWTError:
        raise credentials_exception