"""
Employee accounts and roles.

Replaces `tblemployee` + `previliege.aspx` + `validateuserrole`.

Two confirmed legacy findings this directly fixes:
  1. `sp_getadminbyusernamepass` compares `password` in plaintext
     (INVENTORY-AND-INVOICING.md §9a.4) — `tblemployee.password` is
     `nvarchar(100)`, no hash/salt column. The QA priority memo separately
     flags employee passwords rendering in plaintext on `viewallemployee.aspx`.
     Django's `AbstractUser.password` is always a salted hash (PBKDF2 by
     default); there is no code path in this app that can display it.
  2. `validateuserrole` matches a CSV string (`tblemployee.siterole`) with
     `LIKE '%,'+@roleid+',%'`, parsed elsewhere by a `WHILE`-loop scalar UDF
     — and the *check itself* was only ever wired into 87 of ~130 pages, so
     the other pages had no server-side gate at all (confirmed as a Tier-1
     finding in the priority memo: permission checkboxes only hid UI,
     direct-URL access bypassed them entirely). Django's Group/Permission
     system is enforced by decorators/mixins on every view, not optional
     per-page plumbing someone has to remember to add.
"""

from django.contrib.auth.base_user import AbstractBaseUser, BaseUserManager
from django.contrib.auth.models import PermissionsMixin
from django.db import models

from apps.core.models import TimeStampedModel


class EmployeeManager(BaseUserManager):
    use_in_migrations = True

    def _create_user(self, employee_code, password, **extra_fields):
        if not employee_code:
            raise ValueError("Employees must have an employee_code")
        employee_code = employee_code.strip()
        user = self.model(employee_code=employee_code, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_user(self, employee_code, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", False)
        extra_fields.setdefault("is_superuser", False)
        return self._create_user(employee_code, password, **extra_fields)

    def create_superuser(self, employee_code, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        if extra_fields.get("is_staff") is not True:
            raise ValueError("Superuser must have is_staff=True")
        if extra_fields.get("is_superuser") is not True:
            raise ValueError("Superuser must have is_superuser=True")
        return self._create_user(employee_code, password, **extra_fields)


class Employee(AbstractBaseUser, PermissionsMixin, TimeStampedModel):
    """
    Login identity is `employee_code` (replaces `empid`), not a separate
    username. Role/permission enforcement uses Django's built-in
    Group/Permission machinery — no bespoke CSV-role table.

    Deliberately lean: sensitive PII the legacy `tblemployee` also stored
    in the same row (ssn, bank/account/ifsc, salary, dob, address,
    emergency contacts, blood group, marital status — flagged in
    IADMIN-SYSTEM-REFERENCE.md §9b.4 as the same table that stores
    plaintext passwords also storing government IDs and salary) lives in
    `apps.hr.EmployeeProfile` instead, one-to-one with this model. Keeping
    auth identity and HR PII in separate tables/apps means they can carry
    different permission surfaces — someone who can authenticate staff
    doesn't automatically get read access to salaries and bank details.
    """

    employee_code = models.CharField(max_length=32, unique=True, db_index=True)
    first_name = models.CharField(max_length=150, blank=True)
    last_name = models.CharField(max_length=150, blank=True)
    email = models.EmailField(blank=True)
    is_staff = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)

    default_location = models.ForeignKey(
        "locations.Location",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
        help_text="Pre-selects Scan location on Tracker / Transfer for this employee.",
    )

    objects = EmployeeManager()

    USERNAME_FIELD = "employee_code"
    REQUIRED_FIELDS = []

    class Meta:
        ordering = ["employee_code"]

    def __str__(self):
        full_name = f"{self.first_name} {self.last_name}".strip()
        return f"{self.employee_code} ({full_name})" if full_name else self.employee_code

    def get_full_name(self):
        return f"{self.first_name} {self.last_name}".strip() or self.employee_code

    def get_short_name(self):
        return self.first_name or self.employee_code
