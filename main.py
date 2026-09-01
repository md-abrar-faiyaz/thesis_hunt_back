from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

from routers import auth, inspector, student, faculty

app = FastAPI(title="Thesis Hunt API")

# Configure CORS for local development and live web hosting
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register modular API routers
app.include_router(inspector.router)
app.include_router(auth.router)
app.include_router(student.router)
app.include_router(faculty.router)



if __name__ == "__main__":
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)
