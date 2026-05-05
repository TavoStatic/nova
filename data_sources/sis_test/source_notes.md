# SIS Source Notes

These notes capture the external field-mapping references that best match the live BISD test SIS pipeline.

## Best Match

The live SQL Server references in the local dashboard code use:

- `dbo.REG`
- `dbo.REG_BUILDING`
- `dbo.REG_PROGRAMS`
- `dbo.REG_ENTRY_WITH`

That aligns much more strongly with the **eSchoolPlus** mapping pages than the classic PowerSchool student table naming pages.

## Primary References

- Common eSchoolPlus SIS Student Tables Names and Fields  
  [https://ps.powerschool-docs.com/naviance/latest/common-eschoolplus-sis-student-tables-names-and-fi](https://ps.powerschool-docs.com/naviance/latest/common-eschoolplus-sis-student-tables-names-and-fi)
- eSchoolPlus SIS Student Field Mapping  
  [https://ps.powerschool-docs.com/naviance/latest/eschoolplus-sis-student-field-mapping](https://ps.powerschool-docs.com/naviance/latest/eschoolplus-sis-student-field-mapping)

## Comparison References

- Common PowerSchool SIS Student Table Names and Fields  
  [https://ps.powerschool-docs.com/naviance/latest/common-powerschool-sis-student-table-names-and-fie](https://ps.powerschool-docs.com/naviance/latest/common-powerschool-sis-student-table-names-and-fie)
- PowerSchool SIS Student Field Mapping  
  [https://ps.powerschool-docs.com/naviance/latest/powerschool-sis-student-field-mapping](https://ps.powerschool-docs.com/naviance/latest/powerschool-sis-student-field-mapping)

## Practical Takeaway

Nova should reason about this pipeline primarily with **eSchoolPlus-style field names**, while keeping a lightweight PowerSchool alias layer only for translation and documentation crosswalks.

## Additional Local Grounding

- `dbo.REG` should be treated as the **latest captured student record**.
- `dbo.REG_ENTRY_WITH` should be treated as the **district enrollment history timeline**.
- That makes `dbo.REG_ENTRY_WITH` a strong candidate for:
  - enrollment-history questions
  - current-year grade change history
  - prior campus timeline questions
  - district enrollment presence checks
- If you need to know whether a student had a grade change during the current year, `dbo.REG_ENTRY_WITH` is the better source because it can show when and where that change happened.
- `dbo.REG_ENTRY_WITH` should not replace `dbo.REG` when Nova needs the latest captured student snapshot.

## District Population Grounding

District-provided population flags are grounded in `dbo.REG_PROGRAMS`.

Use `PROGRAM_ID`, `FIELD_NUMBER`, `START_DATE IS NOT NULL`, and `END_DATE IS NULL` to identify active population membership. The current grounded population map lives in:

- `data_sources/sis_test/population_definitions.json`

Known active population keys include:

- `foster`: `PROGRAM_ID = 146`, `FIELD_NUMBER = 31`
- `dyslexia`: `PROGRAM_ID = 146`, `FIELD_NUMBER = 33`
- `military`: `PROGRAM_ID = 146`, `FIELD_NUMBER = 32`
- `plan504`: `PROGRAM_ID = 146`, `FIELD_NUMBER = 116`
- `gt`: `PROGRAM_ID = 146`, `FIELD_NUMBER = 11`
- `parentalper`: `PROGRAM_ID = 146`, `FIELD_NUMBER = 6`
- `ada`: `PROGRAM_ID = 146`, `FIELD_NUMBER = 4`
- `eb`: `PROGRAM_ID = 146`, `FIELD_NUMBER = 5`
- `immigrant`: `PROGRAM_ID = 146`, `FIELD_NUMBER = 12`
- `intervention`: `PROGRAM_ID = 146`, `FIELD_NUMBER = 117`
- `at_risk`: `PROGRAM_ID = 146`, `FIELD_NUMBER = 7`
- `sped`: `PROGRAM_ID = 148`, `FIELD_NUMBER = 4`
