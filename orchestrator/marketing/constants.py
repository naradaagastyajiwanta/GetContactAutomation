from enum import Enum


class ClientType(str, Enum):
    LEMBAGA_NEGARA = "lembaga_negara"
    KEMENTERIAN = "kementerian"
    BUMN = "bumn"
    SWASTA_BESAR = "swasta_besar"
    ASOSIASI = "asosiasi"
    LPK = "lpk"
    LKP = "lkp"


class GroupStatus(str, Enum):
    DRAFT = "draft"
    SEARCHING = "searching"
    DONE = "done"


class SearchStatus(str, Enum):
    PENDING = "pending"
    SEARCHING = "searching"
    FOUND = "found"
    NOT_FOUND = "not_found"


class ContactType(str, Enum):
    WA_PHONE = "wa_phone"
    EMAIL = "email"
    OFFICE_PHONE = "office_phone"
    PIC_NAME = "pic_name"
    PIC_TITLE = "pic_title"
