class SkillError(Exception):
    pass


class SkillValidationError(SkillError, ValueError):
    pass


class SkillNotFoundError(SkillError, LookupError):
    pass
