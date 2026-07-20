# REI_Research
A batch of python scripts that use free, public government sites to pull data on addresses.

`
Example command:

python research/01_address_normalization.py "4202 Marc Ave., Edinburg, TX 78539" --pretty

Example output:

{
  "original_address": "4202 Marc Ave., Edinburg, TX 78539",
  "normalized_address": "4202 Marc Ave, Edinburg, TX 78539",
  "street": "4202 Marc Ave",
  "street_number": "4202",
  "street_name": "Marc Ave",
  "city": "Edinburg",
  "state": "TX",
  "zip": "78539",
  "county": "Hidalgo County",
  "county_fips": "48215",
  "latitude": 26.283414490742,
  "longitude": -98.200830076934
}
`
