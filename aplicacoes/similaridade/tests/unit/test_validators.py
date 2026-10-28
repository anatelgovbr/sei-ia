import pytest
import pandas as pd
from api_sei.pydantic_models.validators import pandas_dataframe_validator

def test_pandas_dataframe_validator_with_valid_dataframe():
    df = pd.DataFrame({'col1': [1, 2], 'col2': [3, 4]})
    assert pandas_dataframe_validator(df) is df

def test_pandas_dataframe_validator_with_invalid_type():
    invalid_data = "not a dataframe"
    with pytest.raises(ValueError, match='O valor deve ser um objeto pandas.DataFrame'):
        pandas_dataframe_validator(invalid_data)

def test_pandas_dataframe_validator_with_none():
    with pytest.raises(ValueError, match='O valor deve ser um objeto pandas.DataFrame'):
        pandas_dataframe_validator(None)

def test_pandas_dataframe_validator_with_empty_dataframe():
    df = pd.DataFrame()
    assert pandas_dataframe_validator(df) is df

def test_pandas_dataframe_validator_with_series():
    series = pd.Series([1, 2, 3])
    with pytest.raises(ValueError, match='O valor deve ser um objeto pandas.DataFrame'):
        pandas_dataframe_validator(series)
