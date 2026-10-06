import os
from typing import List, Literal
from pydantic import BaseModel, Field
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate


class CategoryScore(BaseModel):
    name: Literal["Content", "Structure", "Skills", "Impact", "ATS Compatibility"]
    score: int = Field(description="Score from 0 to 100")
    comment: str = Field(description="One sentence explaining this score")


class ATSCheck(BaseModel):
    label: str = Field(description="Short check name, e.g. 'Contact details present'")
    passed: bool
    note: str = Field(description="One short sentence if failed, empty string if passed")


class Issue(BaseModel):
    priority: Literal["High", "Medium", "Low"]
    title: str = Field(description="Short headline of the problem")
    problem: str = Field(description="What is wrong and why it hurts the resume")
    fix: str = Field(description="Exactly what to do about it")
    before: str = Field(
        description="A short EXACT quote from the resume showing the problem, or empty string"
    )
    after: str = Field(
        description="Improved rewrite of that quote. Use [placeholders] for facts not in the resume, or empty string"
    )


class ResumeFeedback(BaseModel):
    overall_score: int = Field(description="Score from 0 to 100")
    verdict: Literal["Excellent", "Strong", "Good", "Needs work", "Weak"]
    summary: str = Field(description="2-3 sentence overall impression")
    category_scores: List[CategoryScore] = Field(
        description="Exactly 5 entries: Content, Structure, Skills, Impact, ATS Compatibility"
    )
    ats_checks: List[ATSCheck] = Field(description="5 to 7 checks")
    strengths: List[str]
    issues: List[Issue] = Field(description="4 to 7 issues, High priority first")
    detected_skills: List[str]
    missing_skills: List[str] = Field(
        description="Skills commonly expected for the target role that are absent"
    )


SYSTEM_PROMPT = """You are an expert recruiter and resume coach.
Review the resume text and be honest, specific, and practical.

Rules:
- Base everything ONLY on the resume text. Never invent experience.
- For "before", copy a short exact phrase from the resume. For "after",
  rewrite it, and use placeholders like [number] or [tool] for any detail
  that is not in the resume. Never make up metrics, tools, or employers.
- ATS checks can only judge what is visible in the text: contact details,
  standard section headings, dates, reasonable length, clear bullet points,
  consistent formatting.
- Order issues from High to Low priority. High means it could cost an interview.
- Score fairly. Most resumes land between 50 and 80. The verdict must match
  the score: 85+ Excellent, 75-84 Strong, 60-74 Good, 40-59 Needs work, below 40 Weak.
- Adapt skills and advice to the target role and job description when provided.
  Compare requirements with resume evidence, but never claim the applicant has
  a skill or experience that is not supported by the resume. If no target role
  is given, infer the field from the resume."""

prompt = ChatPromptTemplate.from_messages([
    ("system", SYSTEM_PROMPT),
    ("human", "Target role (may be empty): {role}\n\nJob description (optional):\n{job_description}\n\nResume:\n{resume_text}"),
])

llm = ChatOpenAI(
    model="openai/gpt-oss-120b",
    base_url="https://api.groq.com/openai/v1",
    api_key=os.getenv("GROQ_API_KEY"),
    temperature=0.2,
)

chain = prompt | llm.with_structured_output(
    ResumeFeedback, method="function_calling"
)


def analyze_resume(resume_text: str, role: str = "", job_description: str = "") -> dict:
    result = chain.invoke({
        "resume_text": resume_text[:12000],
        "role": role or "Not specified",
        "job_description": job_description[:6000] or "Not provided",
    })
    return result.model_dump()


def write_resume_content(action: str, content: str, role: str = "") -> str:
    instructions = {
        "bullet": "Rewrite the supplied resume bullet as one concise, impact-focused bullet. Do not invent facts, numbers, or tools. Use [placeholder] only where a measurable detail is missing.",
        "summary": "Write a concise professional resume summary using only the supplied facts. Do not invent credentials, years, achievements, or tools.",
        "skills": "Suggest up to 10 relevant resume skills for the supplied job title. Return only a comma-separated list and do not claim the person already has them.",
    }
    if action not in instructions:
        raise ValueError("Unsupported resume writing action.")
    prompt_text = (
        f"{instructions[action]}\n"
        f"Target role: {role or 'Not specified'}\n"
        f"User-provided context:\n{content[:3000]}"
    )
    response = llm.invoke(prompt_text)
    result = response.content
    if not isinstance(result, str) or not result.strip():
        raise ValueError("The writing helper returned no text.")
    return result.strip()