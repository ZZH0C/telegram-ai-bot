SYSTEM_PROMPT = (
    "Your answer should contain minimal required info. Less is better. "
    "It should contain less than 1200 characters. Be direct and concise."
)

ANALYZE_PROMPT_EN = (
    "Analyze these messages. Tell me which user was right if there was some debate "
    "and give me links to proofs why he is right. Be objective, concise, and format nicely.\n\n"
    "Messages:\n{messages}"
)

ANALYZE_PROMPT_RU = (
    "Проанализируй эти сообщения. Скажи, кто из пользователей был прав, если был спор, "
    "и дай ссылки на доказательства, почему он прав. Будь объективным, кратким и оформи ответ красиво.\n\n"
    "Сообщения:\n{messages}"
)
