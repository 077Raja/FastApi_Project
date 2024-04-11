from datetime import datetime, timedelta
import re
from typing import List, Optional
from mongoengine import Q
from fastapi import FastAPI, HTTPException, Path, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pymongo import MongoClient
from bson import ObjectId
from pydantic import BaseModel, Field
from bson.errors import InvalidId
from requests import session
from starlette.middleware.sessions import SessionMiddleware
import os

port = os.getenv('PORT')

if port is None:
    port = 8000 

port = int(port)

print("The port number is:", port)


dburl = "mongodb+srv://raja:thakur@cluster0.i8xo5zs.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0"
# dburl = "mongodb://localhost:27017/library"
client = MongoClient(dburl)
db = client["library"]
books_collection = db["books"]
users_collection = db["users"]
admins_collection = db["admins"]

app = FastAPI()

app.add_middleware(SessionMiddleware, secret_key="secret_key")

app.mount("/static", StaticFiles(directory="static"), name="static")

templates = Jinja2Templates(directory="templates")



class Book(BaseModel):
    id: Optional[str] = Field(None, alias="_id")
    title: str
    author: str
    quantity: int
    section: str
    serialno: List[int]
    issued_on: Optional[datetime]
    to_be_returned: Optional[datetime]
    issued_by: Optional[str]

    class Config:
        arbitrary_types_allowed = True
        json_encoders = {ObjectId: str}


class User(BaseModel):
    name: str
    username: str
    password: str
    number: int
    email: str
    books: List[int]
    books_issued: List[str] = []

    class Config:
        arbitrary_types_allowed = True
        json_encoders = {ObjectId: str}


class Admin(BaseModel):
    username: str
    password: str


@app.get("/")
async def home(req:Request):
    return templates.TemplateResponse(name="home.html", context={"request":req})


@app.get("/signup", response_class=HTMLResponse)
async def signup(request: Request):
    return templates.TemplateResponse("sign-up.html", {"request": request})

@app.post("/signed_up", response_class=HTMLResponse)
async def signed_up(request: Request, name: str = Form(...), user: str = Form(...), 
                    password: str = Form(...), rep_password: str = Form(...), 
                    number: int = Form(...), email: str = Form(...)):
    if not (name and user and password and rep_password and number and email):
        raise HTTPException(status_code=400, detail="Fill All The Fields")

    if password != rep_password:
        raise HTTPException(status_code=400, detail="Passwords Don't Match")

    
    existing_user = users_collection.find_one({"$or": [{"name": name}, {"number": number}]})
    if existing_user:
        raise HTTPException(status_code=400, detail="User already registered")

   
    existing_username = users_collection.find_one({"username": user})
    if existing_username:
        raise HTTPException(status_code=400, detail="Please choose a different Username")

    
    new_user = {
        "name": name,
        "username": user,
        "password": password,
        "number": number,
        "email": email,
        "books": []
    }
    users_collection.insert_one(new_user)
    return templates.TemplateResponse("logged-in.html", {"user": new_user, "time": "first", "request": request})

@app.get("/login", response_class=HTMLResponse)
async def login(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})

@app.post("/logged_in", response_class=HTMLResponse)
async def logged_in(request: Request, user: str = Form(...), password: str = Form(...)):
    if 'user' in request.session:
        return templates.TemplateResponse("logged-in.html", {"user": request.session['user'], "time": None, "request": request})

    if not user or not password:
        raise HTTPException(status_code=400, detail="Please Fill All The Details")

    user_data = users_collection.find_one({"username": user, "password": password})
    if not user_data:
        raise HTTPException(status_code=400, detail="Invalid credentials")
    else:
        request.session['user'] = user_data["username"]
        return templates.TemplateResponse("logged-in.html", {"user": user_data["username"], "time": "first", "request": request})


@app.get("/logout", response_class=HTMLResponse)
async def logout(request: Request):
    return templates.TemplateResponse("home.html", {"request": request})


@app.post("/admin/login", response_class=HTMLResponse)
async def admin_login(request: Request, username: str = Form(...), password: str = Form(...)):
    if 'admin' in request.session:
        return templates.TemplateResponse("admin.html", {"user": request.session['admin'], "request": request})

    elif username and password:
        admin_data = admins_collection.find_one({"username": username, "password": password})
        if not admin_data:
            raise HTTPException(status_code=400, detail="Invalid credentials")
        else:
            request.session['admin'] = admin_data["username"]
            return templates.TemplateResponse("/admin123", {"user": admin_data["username"], "request": request})
    else:
        return templates.TemplateResponse("admin-login.html", {"request": request})


@app.post("/admin/register", response_model=Admin)
async def admin_register(admin: Admin):
    new_admin = admin.dict()
    result = admins_collection.insert_one(new_admin)
    return admin

def create_admin_if_not_exists():
    admin_exists = Admin.objects(username='admin').first()
    if not admin_exists:
        admin = Admin(username='admin', password='admin')
        admin.save()
        return {"message": "Admin created successfully"}
    else:
        return {"message": "Admin already exists"}



@app.post("/add_books", response_class=HTMLResponse)
async def add_books(request: Request, name: str = Form(...), author: str = Form(...),
                     quantity: int = Form(...), section: str = Form(...),
                     serialno: str = Form(...)):
    if 'admin' in request.session:
        if not (name and author and quantity and section and serialno):
            raise HTTPException(status_code=400, detail="Please Fill All Fields")

        book_data = books_collection.find_one({"title": name, "author": author})
        if book_data:
            books_collection.update_one(
                {"_id": book_data["_id"]},
                {"$inc": {"quantity": quantity}, "$push": {"serialno": {"$each": [int(i) for i in re.findall('[0-9]+', serialno)]}}}
            )
        else:
            book = {
                "title": name,
                "author": author,
                "quantity": quantity,
                "section": section,
                "serialno": [int(i) for i in re.findall('[0-9]+', serialno)],
                "issued_on": datetime.now(),
                "to_be_returned": datetime.now(),
                "issued_by": list(admins_collection.find())[0]["username"]
            }
            books_collection.insert_one(book)

        return templates.TemplateResponse("add-books.html", {"request": request, "message": "The Book has been Successfully Added"})

    else:
        return RedirectResponse("/admin", status_code=303)
    

@app.get("/books/{book_id}", response_model=Book)
async def read_book(book_id: str = Path(...)):
    if not ObjectId.is_valid(book_id):
        raise HTTPException(status_code=400, detail="Invalid book ID format")
        
    book = books_collection.find_one({"_id": ObjectId(book_id)})
    if book:
       
        book["_id"] = str(book["_id"])
        return Book(**book)
    else:
        raise HTTPException(status_code=404, detail="Book not found")


@app.get("/books/", response_model=List[Book])
async def list_books():
    books = books_collection.find()
    formatted_books = []
    for book in books:
        book['_id'] = str(book['_id']) 
        formatted_books.append(book)
    return formatted_books


@app.put("/books/{book_id}", response_model=Book)
async def update_book(book_id: str = Path(...), book: Book = None):
    if book is None:
        raise HTTPException(status_code=400, detail="Invalid Book data")

   
    existing_book = books_collection.find_one({"_id": ObjectId(book_id)})
    if existing_book is None:
        raise HTTPException(status_code=404, detail="Book not found")

  
    update_result = books_collection.update_one(
        {"_id": ObjectId(book_id)}, {"$set": book.dict(exclude_unset=True)}
    )
    if update_result.modified_count == 1:
       
        updated_book = books_collection.find_one({"_id": ObjectId(book_id)})
        updated_book["_id"] = str(updated_book["_id"])  # Convert ObjectId to string
        return Book(**updated_book)
    else:
        raise HTTPException(status_code=500, detail="Failed to update book")


@app.delete("/books/{book_id}", status_code=204)
async def delete_book(book_id: str = Path(...)):
    delete_result = books_collection.delete_one({"_id": ObjectId(book_id)})
    if delete_result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Book not found")
    return


@app.get("/search/")
def search_books(Query: str):
    if 'author:' in Query:
        q = re.findall('author:(.+)', Query)
        if q:
            books = [book for book in list_books() if q[0] in book.author]
            return search_object(books)

    elif 'title:' in Query:
        q = re.findall('title:(.+)', Query)
        if q:
            books = [book for book in list_books() if q[0] in book.name]
            return search_object(books)

    return []

def search_object(books):
    result = []
    for book in books:
        result.append(book.name)  
    return result

@app.get("/issue_book", response_class=HTMLResponse)
async def issue_book(request: Request, username: str, serialno: int) -> HTMLResponse:
    user = users_collection.find_one({"username": username})
    if not user:
        raise HTTPException(status_code=400, detail="Username is Wrong")

    book = books_collection.find_one({"serialno": serialno})
    if not book:
        raise HTTPException(status_code=400, detail="Serial No. Not In Database")

    if book["quantity"] == 0:
        raise HTTPException(status_code=400, detail="The Book Is Not Available")

    if serialno in user["books"]:
        raise HTTPException(status_code=400, detail="The User already issued this Book")

    
    books_collection.update_one(
        {"serialno": serialno},
        {"$inc": {"quantity": -1},
         "$set": {"issued_on": datetime.today(),
                  "to_be_returned": datetime.today() + timedelta(days=7)}}
    )


    users_collection.update_one(
        {"username": username},
        {"$push": {"books": serialno}}
    )

    return templates.TemplateResponse("issue-books.html", {"request": request, "message": "Book Successfully Issued"})

@app.get("/books/by_serial/{serialno}", response_model=Book)
async def get_book_by_serial(serialno: int):
    book = books_collection.find_one({"serialno": serialno})
    if book:
        
        book["_id"] = str(book["_id"])
        return Book(**book)
    else:
        raise HTTPException(status_code=404, detail="Book not found")

@app.post("/book_issue_return", response_class=HTMLResponse)
async def book_issue_return(request: Request, username: str = Form(...), 
                            serialno: int = Form(...), action: str = Form(...)):
    
    if 'admin' in request.session:
        if not (username and serialno and action):
            raise HTTPException(status_code=400, detail="Please Fill All The Fields")

        user = users_collection.find_one({"username": username})
        if not user:
            raise HTTPException(status_code=400, detail="Username is Wrong")

        book = books_collection.find_one({"serialno": serialno})
        if not book:
            raise HTTPException(status_code=400, detail="Serial No. Not In Database")

        if action == 'Issue':
            if book["quantity"] == 0:
                raise HTTPException(status_code=400, detail="The Book Is Not Available")

            if serialno in user["books"]:
                raise HTTPException(status_code=400, detail="The User already issued this Book")

            
            books_collection.update_one(
                {"serialno": serialno},
                {"$inc": {"quantity": -1},
                 "$set": {"issued_on": datetime.today(),
                          "to_be_returned": datetime.today() + timedelta(days=7)}}
            )

           
            users_collection.update_one(
                {"username": username},
                {"$push": {"books": serialno}}
            )

            return templates.TemplateResponse("issue-book.html", {"request": request, "message": "Book Successfully Issued"})

        elif action == 'Return':
            if serialno not in user["books"]:
                raise HTTPException(status_code=400, detail="The User never issued this Book")

            users_collection.update_one(
                {"username": username},
                {"$pull": {"books": serialno}}
            )
            books_collection.update_one(
                {"serialno": serialno},
                {"$inc": {"quantity": 1}}
            )

            return templates.TemplateResponse("issue-book.html", {"request": request, "message": "Book Successfully Returned"})

    else:
        return RedirectResponse("/admin/login", status_code=303)



@app.post("/users/", response_model=User)
async def create_user(user: User):
    
    existing_user = users_collection.find_one({"username": user.username})
    if existing_user:
        raise HTTPException(status_code=400, detail="Username already exists")

   
    if not all(isinstance(book, int) for book in user.books):
        raise HTTPException(status_code=422, detail="Invalid book IDs. All book IDs should be integers.")

   
    new_user = user.dict()
    result = users_collection.insert_one(new_user)
    return user


@app.get("/users/{username}", response_model=User)
async def read_user(username: str = Path(...)):
    user = users_collection.find_one({"username": username})
    if user:
        return User(**user)
    else:
        raise HTTPException(status_code=404, detail="User not found")

@app.get("/users/", response_model=List[User])
async def list_users():
    users = users_collection.find()
    return [User(**user) for user in users]


@app.delete("/users/{user_id}", status_code=204)
async def delete_user(user_id: str = Path(...)):
    try:
        
        user_object_id = ObjectId(user_id)
    except InvalidId:
        raise HTTPException(status_code=400, detail="Invalid user ID format")

   
    delete_result = users_collection.delete_one({"_id": user_object_id})
    if delete_result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="User not found")

@app.get("/change_user", response_class=HTMLResponse)
async def logout(request: Request):
    return templates.TemplateResponse("change-user.html", {"request": request})


@app.put("/change_password", response_class=HTMLResponse)
async def change_password(request: Request, username: str = Form(...), 
                          old_password: str = Form(...), new_password: str = Form(...)):
    if not (username and old_password and new_password):
        raise HTTPException(status_code=400, detail="Please fill all the fields")

    user_data = users_collection.find_one({"username": username, "password": old_password})
    if not user_data:
        raise HTTPException(status_code=400, detail="Invalid credentials")

    # Update the user's password
    users_collection.update_one(
        {"username": username},
        {"$set": {"password": new_password}}
    )
    return templates.TemplateResponse("login.html", {"request": request, "message": "Password changed successfully"})

if __name__ == '__main__':
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=port)
