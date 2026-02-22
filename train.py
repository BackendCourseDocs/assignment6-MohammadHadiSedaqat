from fastapi import FastAPI, Query, Form, File, UploadFile, HTTPException
from fastapi.staticfiles import StaticFiles
import requests
from pydantic import BaseModel, Field
from typing import Optional
import os
import shutil
import psycopg2

conn = psycopg2.connect(
    dbname="books", user="hadisedaghat", password="", host="localhost", port="5432"
)
cursor = conn.cursor()


class BookValidation(BaseModel):
    title: str = Field(..., min_length=3, max_length=100)
    author: str = Field(..., min_length=3, max_length=100)
    publisher: str = Field(..., min_length=3, max_length=100)
    first_publish_year: int = Field(..., ge=0)
    image_url: Optional[str] = None


os.makedirs("images", exist_ok=True)
app = FastAPI()
app.mount("/images", StaticFiles(directory="images"), name="images")

url = "https://openlibrary.org/search.json"
params = {"q": "python", "limit": 58}
response = requests.get(url, params=params)
data = response.json()


@app.on_event("startup")
def load_initial_data():
    cursor.execute("SELECT COUNT(*) FROM books;")
    count = cursor.fetchone()[0]

    if count == 0:
        url = "https://openlibrary.org/search.json"
        params = {"q": "python", "limit": 50}
        response = requests.get(url, params=params)
        data = response.json()

        books_to_insert = data.get("docs", [])[:50]

        for book in books_to_insert:
            title = book.get("title")
            author = (
                book.get("author_name", ["Unknown"])[0]
                if book.get("author_name")
                else "Unknown"
            )
            publisher = (
                book.get("publisher", ["Unknown"])[0]
                if book.get("publisher")
                else "Unknown"
            )
            first_publish_year = book.get("first_publish_year")

            cursor.execute(
                """
                INSERT INTO books (title, author, publisher, first_publish_year)
                VALUES (%s, %s, %s, %s)
                """,
                (title, author, publisher, first_publish_year),
            )

        conn.commit()


# GET: path or query
@app.get("/books")
async def search_books(
    q: Optional[str] = Query(None, min_length=3, max_length=100),
    skip: int = 0,
    limit: Optional[int] = None,
):
    if q:
        query_like = f"%{q.lower()}%"
        sql = """
            SELECT id, title, author, publisher, first_publish_year, image_url
            FROM books
            WHERE LOWER(title) LIKE %s
               OR LOWER(author) LIKE %s
               OR LOWER(publisher) LIKE %s
               OR CAST(first_publish_year AS TEXT) LIKE %s
            OFFSET %s
        """
        if limit:
            sql += f" LIMIT {limit}"
        cursor.execute(sql, (query_like, query_like, query_like, query_like, skip))
    else:
        sql = "SELECT id, title, author, publisher, first_publish_year, image_url FROM books OFFSET %s"
        if limit:
            sql += f" LIMIT {limit}"
        cursor.execute(sql, (skip,))

    rows = cursor.fetchall()
    results = [
        {
            "id": row[0],
            "title": row[1],
            "author": row[2],
            "publisher": row[3],
            "first_publish_year": row[4],
            "image_url": row[5],
        }
        for row in rows
    ]

    return {
        "query": q,
        "count": len(results),
        "results": results,
        "skip": skip,
        "limit": limit,
    }


# POST: Form or Json
@app.post("/books")
async def add_book(
    title: str = Form(..., min_length=3, max_length=100),
    author: str = Form(..., min_length=3, max_length=100),
    publisher: str = Form(..., min_length=3, max_length=100),
    first_publish_year: int = Form(..., ge=0),
    image: Optional[UploadFile] = File(None),
):
    image_url = None
    if image:
        image_path = f"images/{image.filename}"
        with open(image_path, "wb") as buffer:
            shutil.copyfileobj(image.file, buffer)
        image_url = f"http://127.0.0.1:8000/images/{image.filename}"

    cursor.execute(
        """
        INSERT INTO books (title, author, publisher, first_publish_year, image_url)
        VALUES (%s, %s, %s, %s, %s)
        RETURNING id
        """,
        (title, author, publisher, first_publish_year, image_url),
    )
    new_id = cursor.fetchone()[0]
    conn.commit()

    return {
        "id": new_id,
        "title": title,
        "author": author,
        "publisher": publisher,
        "first_publish_year": first_publish_year,
        "image_url": image_url,
    }
