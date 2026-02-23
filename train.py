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

'''
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
'''


# GET: path or query
@app.get("/books")
async def search_books(
    q: Optional[str] = Query(None, min_length=3, max_length=100),
    skip: int = Query(0, ge=0),
    limit: Optional[int] = Query(10, ge=1, le=100),
):

    sql = "SELECT id, title, author, publisher, first_publish_year, image_url FROM books WHERE 1=1"
    params = []

    if q:
        query_like = f"%{q.lower()}%"
        sql += " AND (LOWER(title) LIKE %s OR LOWER(author) LIKE %s OR LOWER(publisher) LIKE %s OR CAST(first_publish_year AS TEXT) LIKE %s)"
        params.extend([query_like, query_like, query_like, query_like])


    sql += " OFFSET %s LIMIT %s"
    params.extend([skip, limit])

    try:
        cursor.execute(sql, tuple(params))
        rows = cursor.fetchall()
    except Exception as e:
        raise HTTPException(status_code=500, detail="Database query failed")

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


@app.delete("/books/{id}")
async def delete_book(id: int):
    cursor.execute(
        """
        DELETE FROM books
        WHERE id = %s
        RETURNING id, title, author, publisher, first_publish_year, image_url
        """,
        (id,),
    )

    deleted_book = cursor.fetchone()

    if not deleted_book:
        raise HTTPException(status_code=404, detail="Book not found")

    conn.commit()

    return {
        "message": "Book deleted successfully",
        "book": {
            "id": deleted_book[0],
            "title": deleted_book[1],
            "author": deleted_book[2],
            "publisher": deleted_book[3],
            "first_publish_year": deleted_book[4],
            "image_url": deleted_book[5],
        },
    }


# PUT: Path, Form
@app.put("/books/{id}")
async def update_fully_book(
    id: int,
    title: str = Form(..., min_length=3, max_length=100),
    author: str = Form(..., min_length=3, max_length=100),
    publisher: str = Form(..., min_length=3, max_length=100),
    first_publish_year: int = Form(..., ge=0),
    image: Optional[UploadFile] = File(None),
):

    cursor.execute("SELECT image_url FROM books WHERE id = %s", (id,))
    existing = cursor.fetchone()

    if not existing:
        raise HTTPException(status_code=404, detail="Book not found")

    image_url = existing[0]

    if image:
        image_path = f"images/{image.filename}"
        with open(image_path, "wb") as buffer:
            shutil.copyfileobj(image.file, buffer)
        image_url = f"http://127.0.0.1:8000/images/{image.filename}"

    cursor.execute(
        """
        UPDATE books
        SET title = %s,
            author = %s,
            publisher = %s,
            first_publish_year = %s,
            image_url = %s
        WHERE id = %s
        RETURNING id, title, author, publisher, first_publish_year, image_url
        """,
        (title, author, publisher, first_publish_year, image_url, id),
    )

    updated_book = cursor.fetchone()
    conn.commit()

    return {
        "message": "Book fully updated",
        "book": {
            "id": updated_book[0],
            "title": updated_book[1],
            "author": updated_book[2],
            "publisher": updated_book[3],
            "first_publish_year": updated_book[4],
            "image_url": updated_book[5],
        },
    }


# PATCH: query, Form
@app.patch("/books/{id}")
async def update_book_part(
    id: int,
    title: Optional[str] = Form(None),
    author: Optional[str] = Form(None),
    publisher: Optional[str] = Form(None),
    first_publish_year: Optional[int] = Form(None),
    image: Optional[UploadFile] = File(None),
):

    cursor.execute(
        """
        SELECT title, author, publisher, first_publish_year, image_url
        FROM books WHERE id = %s
        """,
        (id,),
    )

    existing = cursor.fetchone()

    if not existing:
        raise HTTPException(status_code=404, detail="Book not found")

    current_title, current_author, current_publisher, current_year, current_image = (
        existing
    )

    new_title = title if title is not None else current_title
    new_author = author if author is not None else current_author
    new_publisher = publisher if publisher is not None else current_publisher
    new_year = first_publish_year if first_publish_year is not None else current_year
    new_image = current_image

    if image:
        image_path = f"images/{image.filename}"
        with open(image_path, "wb") as buffer:
            shutil.copyfileobj(image.file, buffer)
        new_image = f"http://127.0.0.1:8000/images/{image.filename}"

    cursor.execute(
        """
        UPDATE books
        SET title = %s,
            author = %s,
            publisher = %s,
            first_publish_year = %s,
            image_url = %s
        WHERE id = %s
        RETURNING id, title, author, publisher, first_publish_year, image_url
        """,
        (new_title, new_author, new_publisher, new_year, new_image, id),
    )

    updated_book = cursor.fetchone()
    conn.commit()

    return {
        "message": "Book partially updated",
        "book": {
            "id": updated_book[0],
            "title": updated_book[1],
            "author": updated_book[2],
            "publisher": updated_book[3],
            "first_publish_year": updated_book[4],
            "image_url": updated_book[5],
        },
    }
