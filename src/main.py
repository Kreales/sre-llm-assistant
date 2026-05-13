from fastapi import FastAPI

app = FastAPI(
    title="SRE LLM Assistant",
    description="AI-powered log analysis for SRE",
    version="0.1.0"
)

@app.get("/")
async def root():
    return {"status": "ok", "service": "SRE LLM Assistant"}

@app.get("/health")
async def health_check():
    return {"status": "healthy"}
