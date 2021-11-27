import re
from copy import deepcopy
from typing import Dict, List, Tuple

from simple_ddl_parser.utils import check_spec, remove_par

auth = "AUTHORIZATION"


class AfterColumns:
    def p_expression_partition_by(self, p: List) -> None:
        """expr : expr PARTITION BY LP pid RP
        | expr PARTITION BY id LP pid RP
        | expr PARTITION BY pid
        | expr PARTITION BY id pid"""
        p[0] = p[1]
        p_list = list(p)
        _type = None
        if isinstance(p[4], list):
            columns = p[4]
        else:
            columns = p_list[-2]
        if isinstance(p[4], str) and p[4].lower() != "(":
            _type = p[4]
        p[0]["partition_by"] = {"columns": columns, "type": _type}


class Database:
    def p_database_base(self, p: List) -> None:
        """database_base : CREATE DATABASE id
        | database_base clone
        """
        p[0] = p[1]
        p_list = list(p)
        if isinstance(p_list[-1], dict):
            p[0].update(p_list[-1])
        else:
            p[0]["database_name"] = p_list[-1]

    def p_expression_create_database(self, p: List) -> None:
        """expr : expr database_base"""
        p[0] = p[1]
        p_list = list(p)
        p[0].update(p_list[-1])


class TableSpaces:
    @staticmethod
    def get_tablespace_data(p_list):
        if p_list[1] == "TABLESPACE":
            _type = None
            temp = False
        else:
            if p_list[1].upper() == "TEMPORARY":
                _type = None
                temp = True
            else:
                _type = p_list[1]
                if p_list[2].upper() == "TEMPORARY":
                    temp = True
                else:
                    temp = False
        if isinstance(p_list[-1], dict):
            properties = p_list[-1]
            tablespace_name = p_list[-2]
        else:
            properties = None
            tablespace_name = p_list[-1]
        result = {
            "tablespace_name": tablespace_name,
            "properties": properties,
            "type": _type,
            "temporary": temp,
        }
        return result

    def p_expression_create_tablespace(self, p: List) -> None:
        """expr : CREATE TABLESPACE id properties
        | CREATE id TABLESPACE id properties
        | CREATE id TABLESPACE id
        | CREATE TABLESPACE id
        | CREATE id id TABLESPACE id
        | CREATE id id TABLESPACE id properties
        """
        p_list = list(p)
        p[0] = self.get_tablespace_data(p_list[1:])

    def p_properties(self, p: List) -> None:
        """properties : property
        | properties property"""
        p_list = list(p)
        if len(p_list) == 3:
            p[0] = p[1]
            p[0].update(p[2])
        else:
            p[0] = p[1]

    def p_property(self, p: List) -> None:
        """property : id id
        | id STRING
        | id ON
        | id STORAGE
        | id ROW
        """
        p[0] = {p[1]: p[2]}


class Table:
    def p_create_table(self, p: List):
        """create_table : CREATE TABLE IF NOT EXISTS
        | CREATE TABLE
        | CREATE id TABLE IF NOT EXISTS
        | CREATE id TABLE

        """
        # id - for EXTERNAL
        # get schema & table name
        p[0] = {}
        if p[2].upper() == "EXTERNAL":
            p[0] = {"external": True}
        if p[2].upper() == "TEMP" or p[2].upper() == "TEMPORARY":
            p[0] = {"temp": True}


class Column:
    def p_column_property(self, p: List):
        """c_property : id id"""
        p_list = list(p)
        p[0] = {"property": {p_list[1]: p_list[-1]}}

    def set_base_column_propery(self, p: List) -> Dict:

        if "." in list(p):
            type_str = f"{p[2]}.{p[4]}"
        else:
            type_str = p[2]
        if isinstance(p[1], dict):
            p[0] = p[1]
        else:
            size = None
            p[0] = {"name": p[1], "type": type_str, "size": size}
        return p[0]

    @staticmethod
    def parse_complex_type(p_list: List[str]) -> str:
        # for complex <> types
        start_index = 1
        _type = ""
        if isinstance(p_list[1], dict):
            _type = p_list[1]["type"]
            start_index = 2
        for elem in p_list[start_index:]:
            if isinstance(elem, list):
                for _elem in elem:
                    _type += f" {_elem.rstrip()}"
            elif "ARRAY" in elem and elem != "ARRAY":
                _type += elem
            else:
                _type += f" {elem}"
        return _type

    def p_c_type(self, p: List) -> None:
        """c_type : id
        | id id
        | id id id id
        | id id id
        | id DOT id
        | tid
        | ARRAY
        | c_type ARRAY
        | c_type tid
        """
        p[0] = {}
        p_list = remove_par(list(p))
        _type = None

        if len(p_list) == 2:
            _type = p_list[-1]
        elif isinstance(p[1], str) and p[1].lower() == "encode":
            p[0] = {"property": {"encode": p[2]}}
        else:
            _type = self.parse_complex_type(p_list)
        if _type:
            _type = self.process_type(_type, p_list, p)
        p[0]["type"] = _type

    @staticmethod
    def process_type(_type: str, p_list: List, p: List) -> str:
        if isinstance(p_list[-1], str) and p_list[-1].lower() == "distkey":
            p[0] = {"property": {"distkey": True}}
            _type = _type.split("distkey")[0]
        if isinstance(_type, list):
            _type = _type[0]
        _type = _type.strip().replace('" . "', '"."')
        if "<" not in _type and "ARRAY" in _type:
            if "[" not in p_list[-1]:
                _type = _type.replace(" ARRAY", "[]").replace("ARRAY", "[]")
            else:
                _type = _type.replace("ARRAY", "")
        elif "<" in _type and "[]" in _type:
            _type = _type.replace("[]", "ARRAY")
        return _type

    @staticmethod
    def get_size(p_list: List):
        if p_list[-1].isnumeric():
            size = int(p_list[-1])
        else:
            size = p_list[-1]
        if len(p_list) != 3:
            size = (int(p_list[-3]), int(p_list[-1]))
        return size

    @staticmethod
    def get_column_details(p_list: List, p: List):
        if p_list[-1].get("type"):
            p[0]["type"] += f"{p_list[-1]['type'].strip()}"
        elif p_list[-1].get("comment"):
            p[0].update(p_list[-1])
        elif p_list[-1].get("property"):
            for key, value in p_list[-1]["property"].items():
                p[0][key] = value
        p_list.pop(-1)

    def p_column(self, p: List) -> None:
        """column : id c_type
        | column comment
        | column LP id RP
        | column LP id RP c_type
        | column LP id COMMA id RP
        | column LP id COMMA id RP c_type
        """
        p[0] = self.set_base_column_propery(p)
        p_list = remove_par(list(p))

        if isinstance(p_list[-1], dict) and "type" in p_list[-1] and len(p_list) <= 3:
            p[0]["type"] = p_list[-1]["type"]
            if p_list[-1].get("property"):
                for key, value in p_list[-1]["property"].items():
                    p[0][key] = value
        elif isinstance(p_list[-1], dict):
            self.get_column_details(p_list, p)
        self.set_column_size(p_list, p)

    def set_column_size(self, p_list: List, p: List):
        if (
            not isinstance(p_list[-1], dict)
            and bool(re.match(r"[0-9]+", p_list[-1]))
            or p_list[-1] == "max"
        ):
            p[0]["size"] = self.get_size(p_list)

    @staticmethod
    def set_property(p: List) -> List:
        for item in p[1:]:
            if isinstance(item, dict):
                if "property" in item:
                    for key, value in item["property"].items():
                        p[0][key] = value
                    del item["property"]
                p[0].update(item)
        return p

    @staticmethod
    def get_column_properties(p_list: List) -> Tuple:
        pk = False
        nullable = True
        default = None
        unique = False
        references = None
        if isinstance(p_list[-1], str):
            if p_list[-1].upper() == "KEY":
                pk = True
                nullable = False
            elif p_list[-1].upper() == "UNIQUE":
                unique = True
        elif isinstance(p_list[-1], dict) and "references" in p_list[-1]:
            p_list[-1]["references"]["column"] = p_list[-1]["references"]["columns"][0]
            del p_list[-1]["references"]["columns"]
            references = p_list[-1]["references"]
        return pk, default, unique, references, nullable

    def p_defcolumn(self, p: List) -> None:
        """defcolumn : column
        | defcolumn comment
        | defcolumn null
        | defcolumn encode
        | defcolumn PRIMARY KEY
        | defcolumn UNIQUE
        | defcolumn check_ex
        | defcolumn default
        | defcolumn collate
        | defcolumn enforced
        | defcolumn ref
        | defcolumn foreign ref
        | defcolumn encrypt
        | defcolumn generated
        | defcolumn c_property
        | defcolumn on_update
        | defcolumn options
        """
        p[0] = p[1]
        p_list = list(p)

        pk, default, unique, references, nullable = self.get_column_properties(p_list)

        self.set_property(p)

        p[0]["references"] = p[0].get("references", references)
        p[0]["unique"] = unique or p[0].get("unique", unique)
        p[0]["primary_key"] = pk or p[0].get("primary_key", pk)
        p[0]["nullable"] = (
            nullable if nullable is not True else p[0].get("nullable", nullable)
        )
        p[0]["default"] = p[0].get("default", default)
        p[0]["check"] = p[0].get("check", None)
        if isinstance(p_list[-1], dict) and p_list[-1].get("encode"):
            p[0]["encode"] = p[0].get("encode", p_list[-1]["encode"])
        if p[0]["check"]:
            p[0]["check"] = " ".join(p[0]["check"])

    def p_check_ex(self, p: List) -> None:
        """check_ex :  check_st
        | constraint check_st
        """
        name = None
        if isinstance(p[1], dict):
            if "constraint" in p[1]:
                p[0] = {
                    "check": {
                        "constraint_name": p[1]["constraint"]["name"],
                        "statement": " ".join(p[2]["check"]),
                    }
                }
            elif "check" in p[1]:
                p[0] = p[1]
                if isinstance(p[1], list):
                    p[0] = {
                        "check": {"constraint_name": name, "statement": p[1]["check"]}
                    }
                if len(p) >= 3:
                    for item in list(p)[2:]:
                        p[0]["check"]["statement"].append(item)
        else:
            p[0] = {"check": {"statement": [p[2]], "constraint_name": name}}


class Schema:
    def p_expression_schema(self, p: List) -> None:
        """expr : create_schema
        | create_database
        | expr id
        | expr clone
        """
        p[0] = p[1]
        p_list = list(p)

        if isinstance(p_list[-1], dict):
            p[0].update(p_list[-1])
        elif len(p) > 2:
            p[0]["authorization"] = p[2]

    def set_properties_for_schema_and_database(self, p: List, p_list: List) -> None:
        if not p[0].get("properties"):
            if len(p_list) == 3:
                properties = p_list[-1]
            else:
                properties = {p_list[-3]: p_list[-1]}
            p[0]["properties"] = properties
        else:
            p[0]["properties"].update({p_list[-3]: p_list[-1]})

    def set_auth_property_in_schema(self, p: List, p_list: List) -> None:
        if p_list[2] == auth:
            p[0] = {"schema_name": p_list[3], auth.lower(): p_list[3]}
        else:
            p[0] = {"schema_name": p_list[2], auth.lower(): p_list[-1]}

    def p_c_schema(self, p: List) -> None:
        """c_schema : CREATE SCHEMA"""
        pass

    def p_create_schema(self, p: List) -> None:
        """create_schema : c_schema id id
        | c_schema id id id
        | c_schema id
        | c_schema id DOT id
        | c_schema IF NOT EXISTS id
        | c_schema IF NOT EXISTS id DOT id
        | create_schema id id id
        | create_schema id id STRING
        | create_schema options
        """
        p_list = list(p)
        p[0] = {}
        auth_ind = None
        if isinstance(p_list[1], dict):
            p[0] = p_list[1]
            self.set_properties_for_schema_and_database(p, p_list)
        elif auth in p_list:
            auth_ind = p_list.index(auth)
            self.set_auth_property_in_schema(p, p_list)

        if isinstance(p_list[-1], str):
            if auth_ind:
                schema_name = p_list[auth_ind - 1]
                if schema_name is None:
                    schema_name = p_list[auth_ind + 1]

            else:
                schema_name = p_list[-1]

            p[0]["schema_name"] = schema_name.replace("`", "")

        if len(p_list) > 4 and not auth_ind and "." in p_list:
            p[0]["project"] = p_list[-3].replace("`", "")

    def p_create_database(self, p: List) -> None:
        """create_database : CREATE DATABASE id
        | create_database id id id
        | create_database id id STRING
        | create_database options
        """
        p_list = list(p)

        if isinstance(p_list[1], dict):
            p[0] = p_list[1]
            self.set_properties_for_schema_and_database(p, p_list)
        else:
            p[0] = {f"{p[2].lower()}_name": p_list[-1]}


class Drop:
    def p_expression_drop_table(self, p: List) -> None:
        """expr : DROP TABLE id
        | DROP TABLE id DOT id
        """
        # get schema & table name
        p_list = list(p)
        schema = None
        if len(p) > 4:
            if "." in p:
                schema = p_list[-3]
                table_name = p_list[-1]
        else:
            table_name = p_list[-1]
        p[0] = {"schema": schema, "table_name": table_name}


class Type:
    def p_multiple_column_names(self, p: List) -> None:
        """multiple_column_names : column
        | multiple_column_names COMMA
        | multiple_column_names column
        """
        p_list = list(p)
        if isinstance(p[1], dict):
            p[0] = [p[1]]
        else:
            p[0] = p[1]
            if p_list[-1] != ",":
                p[0].append(p_list[-1])

    def p_type_definition(self, p: List) -> None:  # noqa: C901
        """type_definition : type_name id LP pid RP
        | type_name id LP multiple_column_names RP
        | type_name LP id_equals RP
        | type_name TABLE LP defcolumn
        | type_definition COMMA defcolumn
        | type_definition RP
        """
        p_list = remove_par(list(p))
        p[0] = p[1]
        if not p[0].get("properties"):
            p[0]["properties"] = {}

        if "TABLE" in p_list or isinstance(p_list[-1], dict) and p_list[-1].get("name"):
            if not p[0]["properties"].get("columns"):
                p[0]["properties"]["columns"] = []
            p[0]["properties"]["columns"].append(p_list[-1])

        if len(p_list) > 3:
            p[0]["base_type"] = p_list[2]
        else:
            p[0]["base_type"] = None
        if isinstance(p[0]["base_type"], str):
            base_type = p[0]["base_type"].upper()
            if base_type == "ENUM":
                p[0]["properties"]["values"] = p_list[3]
            elif p[0]["base_type"] == "OBJECT":
                if "type" in p_list[3][0]:
                    p[0]["properties"]["attributes"] = p_list[3]
        else:
            if isinstance(p_list[-1], list):
                for item in p_list[-1]:
                    p[0]["properties"].update(item)

    def p_expression_type_as(self, p: List) -> None:
        """expr : type_definition"""
        p[0] = p[1]

    def p_type_name(self, p: List) -> None:
        """type_name : type_create id AS
        | type_create id DOT id AS
        | type_create id DOT id
        | type_create id
        """
        p_list = list(p)
        p[0] = {}
        if "." not in p_list:
            p[0]["schema"] = None
            p[0]["type_name"] = p_list[2]
        else:
            p[0]["schema"] = p[2]
            p[0]["type_name"] = p_list[4]

    def p_type_create(self, p: List) -> None:
        """type_create : CREATE TYPE
        | CREATE OR REPLACE TYPE
        """
        p[0] = None


class Domain:
    def p_expression_domain_as(self, p: List) -> None:
        """expr : domain_name id LP pid RP"""
        p_list = list(p)
        p[0] = p[1]
        p[0]["base_type"] = p[2]
        p[0]["properties"] = {}
        if p[0]["base_type"] == "ENUM":
            p[0]["properties"]["values"] = p_list[4]

    def p_domain_name(self, p: List) -> None:
        """domain_name : CREATE DOMAIN id AS
        | CREATE DOMAIN id DOT id AS
        | CREATE DOMAIN id DOT id
        | CREATE DOMAIN id
        """
        p_list = list(p)
        p[0] = {}
        if "." not in p_list:
            p[0]["schema"] = None
        else:
            p[0]["schema"] = p[3]
        p[0]["domain_name"] = p_list[-2]


class BaseSQL(
    Database, Table, Drop, Domain, Column, AfterColumns, Type, Schema, TableSpaces
):
    def clean_up_id_list_in_equal(self, p_list: List) -> List:
        if isinstance(p_list[1], str) and p_list[1].endswith("="):
            p_list[1] = p_list[1][:-1]
        elif "," in p_list:
            if len(p_list) == 4:
                p_list = p_list[-1].split("=")
            elif len(p_list) == 5 and p_list[-2].endswith("="):
                p_list[-2] = p_list[-2][:-1]
        elif "=" == p_list[-2]:
            p_list.pop(-2)
        return p_list

    def get_property(self, p_list: List) -> Dict:
        _property = None
        if not isinstance(p_list[-2], list):
            _value = True
            value = None
            if p_list[-2]:
                if not p_list[-2] == "=":
                    key = p_list[-2]
                else:
                    key = p_list[-3]

            else:
                _value = False
                key = p_list[-1]
            if "=" in key:
                key = key.split("=")
                if _value:
                    value = f"{key[1]} {p_list[-1]}"
                key = key[0]
            else:
                value = p_list[-1]
            _property = {key: value}
        else:
            _property = p_list[-2][0]
        return _property

    def p_id_equals(self, p: List) -> None:
        """id_equals : id id id
        | id id
        | id_equals COMMA
        | id_equals COMMA id id id
        | id
        | id_equals LP pid RP
        | id_equals LP pid RP id
        | id_equals COMMA id id
        | id_equals COMMA id
        """
        p_list = remove_par(list(p))
        if p_list[-1] == "]":
            p_list = p_list[:-1]
        if isinstance(p_list[-1], list):
            p[0] = p[1]
            p[0][-1][list(p[0][-1].keys())[0]] = p_list[-1]
        else:
            p_list = self.clean_up_id_list_in_equal(p_list)
            _property = self.get_property(p_list)

            if _property:
                if not isinstance(p[1], list):
                    p[0] = [_property]
                else:
                    p[0] = p[1]
                    if not p_list[-1] == ",":
                        p[0].append(_property)

    def p_expression_index(self, p: List) -> None:
        """expr : index_table_name LP index_pid RP"""
        p_list = remove_par(list(p))
        p[0] = p[1]
        for item in ["detailed_columns", "columns"]:
            if item not in p[0]:
                p[0][item] = p_list[-1][item]
            else:
                p[0][item].extend(p_list[-1][item])

    def p_index_table_name(self, p: List) -> None:
        """index_table_name : create_index ON id
        | create_index ON id DOT id
        """
        p[0] = p[1]
        p_list = list(p)
        schema = None
        if "." in p_list:
            schema = p_list[-3]
            table_name = p_list[-1]
        else:
            table_name = p_list[-1]
        p[0].update({"schema": schema, "table_name": table_name})

    def p_create_index(self, p: List) -> None:
        """create_index : CREATE INDEX id
        | CREATE UNIQUE INDEX id
        | create_index ON id
        | CREATE CLUSTERED INDEX id
        """
        p_list = list(p)
        if "CLUSTERED" in p_list:
            clustered = True
        else:
            clustered = False
        if isinstance(p[1], dict):
            p[0] = p[1]
        else:
            p[0] = {
                "schema": None,
                "index_name": p_list[-1],
                "unique": "UNIQUE" in p_list,
                "clustered": clustered,
            }

    def extract_check_data(self, p, p_list):
        if isinstance(p_list[-1]["check"], list):
            check = " ".join(p_list[-1]["check"])
            if isinstance(check, str):
                check = {"constraint_name": None, "statement": check}
        else:
            check = p_list[-1]["check"]
            p[0] = self.set_constraint(p[0], "checks", check, check["constraint_name"])
        p[0]["checks"].append(check)
        return p[0]

    def p_expression_table(self, p: List) -> None:
        """expr : table_name defcolumn
        | table_name LP defcolumn
        | expr COMMA defcolumn
        | expr COMMA
        | expr COMMA constraint
        | expr COMMA check_ex
        | expr COMMA foreign
        | expr COMMA pkey
        | expr COMMA uniq
        | expr COMMA statem_by_id
        | expr COMMA constraint uniq
        | expr COMMA period_for
        | expr COMMA pkey_constraint
        | expr COMMA constraint pkey
        | expr COMMA constraint pkey enforced
        | expr COMMA constraint foreign ref
        | expr COMMA foreign ref
        | expr COMMA table_properties
        | expr encode
        | expr RP
        """
        p[0] = p[1]
        p_list = list(p)
        if p_list[-1] != "," and p_list[-1] != ")":
            if "type" in p_list[-1] and "name" in p_list[-1]:
                p[0]["columns"].append(p_list[-1])
            elif "check" in p_list[-1]:
                p[0] = self.extract_check_data(p, p_list)
            elif "enforced" in p_list[-1]:
                p_list[-2].update(p_list[-1])
                p[0].update({"primary_key_enforced": p_list[-1]["enforced"]})
            else:
                p[0].update(p_list[-1])

        if isinstance(p_list[-1], dict):
            if "constraint" in p_list[-2]:
                if p_list[-1].get("unique_statement"):
                    p[0] = self.set_constraint(
                        p[0],
                        "uniques",
                        {"columns": p_list[-1]["unique_statement"]},
                        p_list[-2]["constraint"]["name"],
                    )
                else:
                    p[0] = self.set_constraint(
                        p[0],
                        "primary_keys",
                        {"columns": p_list[-1]["primary_key"]},
                        p_list[-2]["constraint"]["name"],
                    )
            elif (
                len(p_list) >= 4
                and isinstance(p_list[3], dict)
                and p_list[3].get("constraint")
                and p_list[3]["constraint"].get("primary_key")
            ):
                del p_list[3]["constraint"]["primary_key"]
                p[0] = self.set_constraint(
                    target_dict=p[0],
                    _type="primary_keys",
                    constraint=p_list[3]["constraint"],
                    constraint_name=p_list[3]["constraint"]["name"],
                )
                del p[0]["constraint"]
            elif p_list[-1].get("references"):
                p[0] = self.add_ref_information_to_table(p, p_list)

    def add_ref_information_to_table(self, p, p_list):
        if len(p_list) > 4 and "constraint" in p_list[3]:
            p[0] = self.set_constraint(
                p[0],
                "references",
                p_list[-1]["references"],
                p_list[3]["constraint"]["name"],
            )
        elif isinstance(p_list[-2], list):
            if "ref_columns" not in p[0]:
                p[0]["ref_columns"] = []

            for num, column in enumerate(p_list[-2]):
                ref = deepcopy(p_list[-1]["references"])
                ref["column"] = ref["columns"][num]
                del ref["columns"]
                ref["name"] = column
                p[0]["ref_columns"].append(ref)
        return p[0]

    @staticmethod
    def set_constraint(
        target_dict: Dict, _type: str, constraint: Dict, constraint_name: str
    ) -> Dict:
        if not target_dict.get("constraints"):
            target_dict["constraints"] = {}
        if not target_dict["constraints"].get(_type):
            target_dict["constraints"][_type] = []
        if "name" in constraint:
            del constraint["name"]
        constraint.update({"constraint_name": constraint_name})
        target_dict["constraints"][_type].append(constraint)
        return target_dict

    def p_likke(self, p: List) -> None:
        """likke : LIKE
        | CLONE
        """
        p[0] = None

    def p_expression_like_table(self, p: List) -> None:
        """expr : table_name likke id
        | table_name likke id DOT id
        | table_name LP likke id DOT id RP
        | table_name LP likke id RP
        """
        # get schema & table name
        p_list = remove_par(list(p))
        if len(p_list) > 4:
            if "." in p:
                schema = p_list[-3]
                table_name = p_list[-1]
        else:
            table_name = p_list[-1]
            schema = None
        p[0] = p[1]
        p[0].update({"like": {"schema": schema, "table_name": table_name}})

    def p_t_name(self, p: List) -> None:
        """t_name : id DOT id
        | id
        | id DOT id DOT id
        """
        p_list = list(p)

        project = None

        if len(p) > 3:
            if "." in p:
                schema = p_list[-3]
                table_name = p_list[-1]
                if len(p) == 6:
                    project = p_list[1]
        else:
            table_name = p_list[-1]
            schema = None

        p[0] = {"schema": schema, "table_name": table_name, "columns": [], "checks": []}

        if project:
            p[0]["project"] = project

    def p_table_name(self, p: List) -> None:
        """table_name : create_table t_name
        | table_name likke id
        """
        # can contain additional properties like 'external for HQL
        p[0] = p[1]

        p[0].update(list(p)[-1])

    def p_expression_seq(self, p: List) -> None:
        """expr : seq_name
        | expr INCREMENT id
        | expr INCREMENT id id
        | expr START id
        | expr START id id
        | expr MINVALUE id
        | expr MAXVALUE id
        | expr CACHE id
        | expr CACHE
        """
        # get schema & table name
        p_list = list(p)
        p[0] = p[1]
        if len(p) == 4:
            p[0].update({p[2].lower(): int(p_list[-1])})
        if len(p) == 3:
            p[0].update({p[2].lower(): True})
        elif len(p) == 5:
            p[0].update({f"{p[2].lower()}_{p[3].lower()}": int(p_list[-1])})

    def p_seq_name(self, p: List) -> None:
        """seq_name : create_seq id DOT id
        | create_seq id
        """
        # get schema & table name
        p_list = list(p)
        schema = None
        if len(p) > 4:
            if "." in p:
                schema = p_list[-3]
                seq_name = p_list[-1]
        else:
            seq_name = p_list[-1]
        p[0] = {"schema": schema, "sequence_name": seq_name}

    def p_create_seq(self, p: List) -> None:
        """create_seq : CREATE SEQUENCE IF NOT EXISTS
        | CREATE SEQUENCE

        """
        # get schema & table name
        pass

    def p_tid(self, p: List) -> None:
        """tid : LT id
        | LT
        | tid LT
        | tid id
        | tid COMMAT
        | tid RT
        """
        if not isinstance(p[1], list):
            p[0] = [p[1]]
        else:
            p[0] = p[1]

        for i in list(p)[2:]:
            if not i == "[]" and not i == ",":
                p[0][0] += f" {i}"
            else:
                p[0][0] += f"{i}"

    @staticmethod
    def get_complex_type(p, p_list):
        if len(p_list) == 4:
            p[0]["type"] = f"{p[2]} {p[3][0]}"
        elif p[0]["type"]:
            if len(p[0]["type"]) == 1 and isinstance(p[0]["type"], list):
                p[0]["type"] = p[0]["type"][0]
            p[0]["type"] = f'{p[0]["type"]} {p_list[-1][0]}'
        else:
            p[0]["type"] = p_list[-1][0]
        return p[0]

    def extract_references(self, table_data: Dict):
        ref = {
            "table": table_data["table_name"],
            "columns": [None],
            "schema": table_data["schema"],
            "on_delete": None,
            "on_update": None,
            "deferrable_initially": None,
        }

        if table_data.get("project"):
            ref["project"] = table_data["project"]

        return ref

    def p_null(self, p: List) -> None:
        """null : NULL
        | NOT NULL
        """
        nullable = True
        if "NULL" in p or "null" in p:
            if "NOT" in p or "not" in p:
                nullable = False
        p[0] = {"nullable": nullable}

    def p_f_call(self, p: List) -> None:
        """f_call : id LP RP
        | id LP f_call RP
        | id LP multi_id RP
        | id LP pid RP
        """
        p_list = list(p)
        if isinstance(p[1], list):
            p[0] = p[1]
            p[0].append(p_list[-1])
        else:
            value = ""
            for elem in p_list[1:]:
                if isinstance(elem, list):
                    elem = ",".join(elem)
                value += elem
            p[0] = value

    def p_multi_id(self, p: List) -> None:
        """multi_id : id
        | multi_id id
        | f_call
        | multi_id f_call
        """
        p_list = list(p)
        if isinstance(p[1], list):
            p[0] = p[1]
            p[0].append(p_list[-1])
        else:
            value = " ".join(p_list[1:])
            p[0] = value

    def p_funct_args(self, p: List) -> None:
        """funct_args : LP multi_id RP"""
        p[0] = {"args": f"({p[2]})"}

    def p_funct_expr(self, p: List) -> None:
        """funct_expr : LP multi_id RP
        | multi_id
        """
        if len(p) > 2:
            p[0] = p[2]
        else:
            p[0] = p[1]

    def p_dot_id(self, p: List) -> None:
        """dot_id : id DOT id"""
        p[0] = f"{p[1]}.{p[3]}"

    def p_default(self, p: List) -> None:
        """default : DEFAULT id
        | DEFAULT STRING
        | DEFAULT NULL
        | default FOR dot_id
        | DEFAULT funct_expr
        | DEFAULT LP pid RP
        | default id
        | default LP RP
        """
        p_list = list(p)

        if len(p_list) == 5 and isinstance(p[3], list):
            default = p[3][0]
        elif "DEFAULT" in p_list and len(p_list) == 4:
            default = f"{p[2]} {p[3]}"
        else:
            default = p[2]

        if not isinstance(default, dict) and default.isnumeric():
            default = int(default)

        if isinstance(p[1], dict):
            p[0] = p[1]
            if "FOR" in default:
                p[0]["default"] = {"next_value_for": p_list[-1]}
            else:
                for i in p[2:]:
                    if isinstance(p[2], str):
                        p[2] = p[2].replace("\\'", "'")
                        if i == ")" or i == "(":
                            p[0]["default"] = str(p[0]["default"]) + f"{i}"
                        else:
                            p[0]["default"] = str(p[0]["default"]) + f" {i}"
                        p[0]["default"] = p[0]["default"].replace("))", ")")
        else:
            p[0] = {"default": default}

    def p_enforced(self, p: List) -> None:
        """enforced : ENFORCED
        | NOT ENFORCED
        """
        p_list = list(p)
        p[0] = {"enforced": len(p_list) == 1}

    def p_collate(self, p: List) -> None:
        """collate : COLLATE id
        | COLLATE STRING
        """
        p_list = list(p)
        p[0] = {"collate": p_list[-1]}

    def p_constraint(self, p: List) -> None:
        """
        constraint : CONSTRAINT id
        """

        p_list = list(p)

        p[0] = {"constraint": {"name": p_list[-1]}}

    def p_generated(self, p: List) -> None:
        """
        generated : gen_always funct_expr
        | gen_always funct_expr id
        | gen_always LP multi_id RP
        | gen_always f_call
        """
        p_list = list(p)
        stored = False
        if len(p) > 3 and p_list[-1].lower() == "stored":
            stored = True
        _as = p[2]
        p[0] = {"generated": {"always": True, "as": _as, "stored": stored}}

    def p_gen_always(self, p: List) -> None:
        """
        gen_always : GENERATED id AS
        """
        p[0] = {"generated": {"always": True}}

    def p_check_st(self, p: List) -> None:
        """check_st : CHECK LP id
        | check_st id
        | check_st STRING
        | check_st id RP
        | check_st STRING RP
        | check_st funct_args
        """
        p_list = remove_par(list(p))
        if isinstance(p[1], dict):
            p[0] = p[1]
        else:
            p[0] = {"check": []}
        for item in p_list[2:]:
            if isinstance(p_list[-1], dict) and p_list[-1].get("args"):
                p[0]["check"][-1] += p_list[-1]["args"]
            else:
                p[0]["check"].append(item)

    def p_expression_alter(self, p: List) -> None:
        """expr : alter_foreign ref
        | alter_check
        | alter_unique
        | alter_default
        """
        p[0] = p[1]
        if len(p) == 3:
            p[0].update(p[2])

    def p_alter_unique(self, p: List) -> None:
        """alter_unique : alt_table UNIQUE LP pid RP
        | alt_table constraint UNIQUE LP pid RP
        """

        p_list = remove_par(list(p))
        p[0] = p[1]
        p[0]["unique"] = {"constraint_name": None, "columns": p_list[-1]}
        if "constraint" in p[2]:
            p[0]["unique"]["constraint_name"] = p[2]["constraint"]["name"]

    @staticmethod
    def get_column_and_value_from_alter(p: List) -> Tuple:

        p_list = remove_par(list(p))

        column = None
        value = None

        if isinstance(p_list[2], str) and "FOR" == p_list[2].upper():
            column = p_list[-1]
        elif p[0].get("default") and p[0]["default"].get("value"):
            value = p[0]["default"]["value"] + " " + p_list[-1]
        else:
            value = p_list[-1]
        return column, value

    def p_alter_default(self, p: List) -> None:
        """alter_default : alt_table id id
        | alt_table constraint id id
        | alt_table id STRING
        | alt_table constraint id STRING
        | alter_default id
        | alter_default FOR pid
        """

        p[0] = p[1]
        column, value = self.get_column_and_value_from_alter(p)

        if "default" not in p[0]:

            p[0]["default"] = {
                "constraint_name": None,
                "columns": column,
                "value": value,
            }
        else:
            p[0]["default"].update(
                {
                    "columns": p[0]["default"].get("column") or column,
                    "value": value or p[0]["default"].get("value"),
                }
            )
        if "constraint" in p[2]:
            p[0]["default"]["constraint_name"] = p[2]["constraint"]["name"]

    def p_pid(self, p: List) -> None:
        """pid :  id
        | STRING
        | pid id
        | pid STRING
        | STRING LP RP
        | id LP RP
        | pid COMMA id
        | pid COMMA STRING
        """
        p_list = list(p)

        if len(p_list) == 4 and isinstance(p[1], str):
            p[0] = ["".join(p[1:])]
        elif not isinstance(p_list[1], list):
            p[0] = [p_list[1]]
        else:
            p[0] = p_list[1]
            p[0].append(p_list[-1])

    def p_alter_check(self, p: List) -> None:
        """alter_check : alt_table check_st
        | alt_table constraint check_st
        """
        p_list = remove_par(list(p))
        p[0] = p[1]
        if isinstance(p[1], dict):
            p[0] = p[1]
        if not p[0].get("check"):
            p[0]["check"] = {"constraint_name": None, "statement": []}
        if isinstance(p[2], dict) and "constraint" in p[2]:
            p[0]["check"]["constraint_name"] = p[2]["constraint"]["name"]
        p[0]["check"]["statement"] = p_list[-1]["check"]

    def p_index_pid(self, p: List) -> None:
        """index_pid :  id
        | index_pid id
        | index_pid COMMA index_pid
        """
        p_list = list(p)
        if len(p_list) == 2:
            detailed_column = {"name": p_list[1], "order": "ASC", "nulls": "LAST"}
            column = p_list[1]
            p[0] = {"detailed_columns": [detailed_column], "columns": [column]}
        else:
            p[0] = p[1]
            if len(p) == 3:
                if p_list[-1] in ["DESC", "ASC"]:
                    p[0]["detailed_columns"][0]["order"] = p_list[-1]
                else:
                    p[0]["detailed_columns"][0]["nulls"] = p_list[-1]

                column = p_list[2]
            elif isinstance(p_list[-1], dict):
                for i in p_list[-1]["columns"]:
                    p[0]["columns"].append(i)
                for i in p_list[-1]["detailed_columns"]:
                    p[0]["detailed_columns"].append(i)

    def p_alter_foreign(self, p: List) -> None:
        """alter_foreign : alt_table foreign
        | alt_table constraint foreign
        """

        p_list = list(p)

        p[0] = p[1]
        if isinstance(p_list[-1], list):
            p[0]["columns"] = [{"name": i} for i in p_list[-1]]
        else:
            column = p_list[-1]

            if not p[0].get("columns"):
                p[0]["columns"] = []
            p[0]["columns"].append(column)

        for column in p[0]["columns"]:
            if isinstance(p_list[2], dict) and "constraint" in p_list[2]:
                column.update({"constraint_name": p_list[2]["constraint"]["name"]})

    def p_alt_table_name(self, p: List) -> None:
        """alt_table : ALTER TABLE t_name ADD"""
        table_data = list(p)[-2]
        p[0] = {
            "alter_table_name": table_data["table_name"],
            "schema": table_data["schema"],
        }
        if table_data.get("project"):
            p[0]["project"] = table_data["project"]

    def p_foreign(self, p):
        # todo: need to redone id lists
        """foreign : FOREIGN KEY LP pid RP
        | FOREIGN KEY"""
        p_list = remove_par(list(p))
        if len(p_list) == 4:
            columns = p_list[-1]
            p[0] = columns

    def p_ref(self, p: List) -> None:
        """ref : REFERENCES t_name
        | ref LP pid RP
        | ref ON DELETE id
        | ref ON UPDATE id
        | ref DEFERRABLE INITIALLY id
        | ref NOT DEFERRABLE
        """
        p_list = remove_par(list(p))
        if isinstance(p[1], dict):
            p[0] = p[1]
            if "ON" not in p_list and "DEFERRABLE" not in p_list:
                p[0]["references"]["columns"] = p_list[-1]
            else:
                p[0]["references"]["columns"] = p[0]["references"].get(
                    "columns", [None]
                )
        else:
            data = {"references": self.extract_references(p_list[-1])}
            p[0] = data
        if "ON" in p_list:
            if "DELETE" in p_list:
                p[0]["references"]["on_delete"] = p_list[-1]
            elif "UPDATE" in p_list:
                p[0]["references"]["on_update"] = p_list[-1]
        elif "DEFERRABLE" in p_list:
            if "NOT" not in p_list:
                p[0]["references"]["deferrable_initially"] = p_list[-1]
            else:
                p[0]["references"]["deferrable_initially"] = "NOT"

    def p_expression_primary_key(self, p):
        "expr : pkey"
        p[0] = p[1]

    def p_uniq(self, p: List) -> None:
        """uniq : UNIQUE LP pid RP"""
        p_list = remove_par(list(p))
        p[0] = {"unique_statement": p_list[-1]}

    def p_statem_by_id(self, p: List) -> None:
        """statem_by_id : id LP pid RP
        | id KEY LP pid RP
        """
        p_list = remove_par(list(p))
        if p[1].upper() == "UNIQUE":
            p[0] = {"unique_statement": p_list[-1]}
        elif p[1].upper() == "CHECK":
            p[0] = {"check": p_list[-1]}
        elif p[1].upper() == "PRIMARY":
            p[0] = {"primary_key": p_list[-1]}

    def p_pkey(self, p: List) -> None:
        """pkey : pkey_statement LP pid RP
        | pkey_statement ID LP pid RP
        """
        p_list = remove_par(list(p))

        columns = []
        p[0] = {}
        if isinstance(p_list[2], str) and "CLUSTERED" == p_list[2]:
            order = None
            column = None
            for item in p_list[-1]:
                if item not in ["ASC", "DESC"]:
                    column = item
                else:
                    order = item
                if column and order:
                    columns.append({"column": column, "order": order})
                    column = None
                    order = None
            p[0]["clustered_primary_key"] = columns

        columns = []
        for item in p_list[-1]:
            if item not in ["ASC", "DESC"]:
                columns.append(item)
            else:
                order = item
        p[0]["primary_key"] = columns

    def p_pkey_statement(self, p: List) -> None:
        """pkey_statement : PRIMARY KEY"""
        p[0] = {"primary_key": None}

    def p_comment(self, p: List) -> None:
        """comment : COMMENT STRING"""
        p_list = remove_par(list(p))
        p[0] = {"comment": check_spec(p_list[-1])}

    def p_tablespace(self, p: List) -> None:
        """tablespace : TABLESPACE id
        | TABLESPACE id properties
        """
        # Initial 5m Next 5m Maxextents Unlimited
        p[0] = self.get_tablespace_data(list(p))

    def p_expr_tablespace(self, p: List) -> None:
        """expr : expr tablespace"""
        p_list = list(p)
        p[0] = p[1]
        p[0]["tablespace"] = p_list[-1]
