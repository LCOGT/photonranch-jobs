import pytest

from src.helpers import get_response, get_current_reservations

def test_get_response():
    message = "test result"
    code = 200
    response = get_response(code, message)
    print(response)
    assert response['body'] == message
    assert response['statusCode'] == code

def test_current_reservations():
    """ Just check for a valid response """
    site = "wmd"  # any valid site will do
    try: 
        current_reservations = get_current_reservations(site)
        # the function should return a list, but it will be a dict (with an
        # error message) if the api call fails
        assert type(current_reservations) == list
    except Exception as e:
        print(e)
        assert False
