import pytest

from src.authorizer import calendar_blocks_user_commands


def test_calendar_blocks_user_commands_1(mocker):
    """ Test that a user with a reservation is not blocked. """

    # Check permissions for this user id.
    user_with_reservation = "user_id_1"

    # Since the user has a reservation (below), expect no blocking. 
    expected_result = False

    # Required parameter for the method being tested, but it doesn't matter 
    # because we end up mocking the api that needed it. 
    site = 'anything'  

    # Note: these are partial examples that omit irrelevant reservation info.
    example_reservations = [
        {
            'creator_id': 'user_id_1', 
            'resourceId': 'saf', 
        }, 
        {
            'creator_id': 'user_id_2', 
            'resourceId': 'saf', 
        }
    ]

    # Mock the api call in calendar_blocks_user_commands to return the above
    # example reservations instead. 
    mocker.patch(
        'src.authorizer.get_current_reservations',
        return_value=example_reservations
    )

    # The function we're testing
    user_blocked = calendar_blocks_user_commands(user_with_reservation, site)

    # Since the user has a reservation, they should not be blocked. 
    assert user_blocked == expected_result

def test_calendar_blocks_user_commands_2(mocker):
    """ Test that a user without a reservation is blocked. """

    # Check permissions for this user id.
    user_with_reservation = "user_id_1"

    # Since the user does not have a reservation (below), expect no blocking. 
    expected_result = True

    # Required parameter for the method being tested, but it doesn't matter 
    # because we end up mocking the api that needed it. 
    site = 'anything'  

    # Note: these are partial examples that omit irrelevant reservation info.
    example_reservations = [
        {
            'creator_id': 'user_id_2', 
            'resourceId': 'saf', 
        }
    ]

    # Mock the api call in calendar_blocks_user_commands to return the above
    # example reservations instead. 
    mocker.patch(
        'src.authorizer.get_current_reservations',
        return_value=example_reservations
    )

    # The function we're testing
    user_blocked = calendar_blocks_user_commands(user_with_reservation, site)

    assert user_blocked == expected_result