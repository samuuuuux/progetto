from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from pydantic import BaseModel
from typing import List
from sqlalchemy import create_engine, Column, Integer, String, Boolean, Date, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
from passlib.context import CryptContext
import datetime

DATABASE_URL = "mysql+pymysql://username:password@localhost/biblioteca"

Base = declarative_base()
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

app = FastAPI()

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True)
    password_hash = Column(String)

class Book(Base):
    __tablename__ = "books"
    id = Column(Integer, primary_key=True, index=True)
    title = Column(String)
    author = Column(String)
    available = Column(Boolean, default=True)

class Loan(Base):
    __tablename__ = "loans"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey('users.id'))
    book_id = Column(Integer, ForeignKey('books.id'))
    loan_date = Column(Date)
    return_date = Column(Date, nullable=True)

Base.metadata.create_all(bind=engine)

class UserCreate(BaseModel):
    username: str
    password: str

class UserInDB(UserCreate):
    id: int

class Token(BaseModel):
    access_token: str
    token_type: str

class BookBase(BaseModel):
    title: str
    author: str

class BookInDB(BookBase):
    id: int
    available: bool

class LoanBase(BaseModel):
    user_id: int
    book_id: int
    loan_date: datetime.date
    return_date: datetime.date = None

class LoanInDB(LoanBase):
    id: int

def get_password_hash(password):
    return pwd_context.hash(password)

def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)

def get_user(db, username: str):
    return db.query(User).filter(User.username == username).first()

def authenticate_user(db, username: str, password: str):
    user = get_user(db, username)
    if not user or not verify_password(password, user.password_hash):
        return False
    return user

def create_access_token(data: dict):
    return "dummy_token"

async def get_current_user(token: str = Depends(oauth2_scheme), db: SessionLocal = Depends(SessionLocal)):
    username = token  # Dummy decoding, replace with actual JWT decode logic
    user = get_user(db, username=username)
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid authentication credentials")
    return user

@app.post("/register", response_model=UserInDB)
def register(user: UserCreate, db: SessionLocal = Depends(SessionLocal)):
    db_user = get_user(db, user.username)
    if db_user:
        raise HTTPException(status_code=400, detail="Username already registered")
    hashed_password = get_password_hash(user.password)
    db_user = User(username=user.username, password_hash=hashed_password)
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    return db_user

@app.post("/token", response_model=Token)
def login(form_data: OAuth2PasswordRequestForm = Depends(), db: SessionLocal = Depends(SessionLocal)):
    user = authenticate_user(db, form_data.username, form_data.password)
    if not user:
        raise HTTPException(status_code=400, detail="Incorrect username or password")
    access_token = create_access_token(data={"sub": user.username})
    return {"access_token": access_token, "token_type": "bearer"}

@app.get("/books", response_model=List[BookInDB])
def read_books(skip: int = 0, limit: int = 10, db: SessionLocal = Depends(SessionLocal)):
    books = db.query(Book).offset(skip).limit(limit).all()
    return books

@app.post("/loans", response_model=LoanInDB)
def create_loan(loan: LoanBase, db: SessionLocal = Depends(SessionLocal), current_user: User = Depends(get_current_user)):
    book = db.query(Book).filter(Book.id == loan.book_id, Book.available == True).first()
    if not book:
        raise HTTPException(status_code=400, detail="Book not available")
    db_loan = Loan(**loan.dict(), loan_date=datetime.date.today())
    book.available = False
    db.add(db_loan)
    db.commit()
    db.refresh(db_loan)
    return db_loan

@app.get("/loans", response_model=List[LoanInDB])
def read_loans(skip: int = 0, limit: int = 10, db: SessionLocal = Depends(SessionLocal), current_user: User = Depends(get_current_user)):
    loans = db.query(Loan).filter(Loan.user_id == current_user.id).offset(skip).limit(limit).all()
    return loans

@app.post("/loans/{loan_id}/return", response_model=LoanInDB)
def return_loan(loan_id: int, db: SessionLocal = Depends(SessionLocal), current_user: User = Depends(get_current_user)):
    loan = db.query(Loan).filter(Loan.id == loan_id, Loan.user_id == current_user.id).first()
    if not loan:
        raise HTTPException(status_code=400, detail="Loan not found")
    loan.return_date = datetime.date.today()
    book = db.query(Book).filter(Book.id == loan.book_id).first()
    book.available = True
    db.commit()
    return loan
