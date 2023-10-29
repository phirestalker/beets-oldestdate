import datetime
from dateutil import parser


class DateWrapper(datetime.datetime):
    """
    Wrapper class for datetime objects.
    Allows comparison between dates,
    with the month and day being optional.
    """

    def __new__(cls, y: int = None, m: int = None, d: int = None, iso_string: str = None):
        """
        Create a new datetime object using a convenience wrapper.
        Must specify at least one of either year or iso_string.
        :param y: The year, as an integer
        :param m: The month, as an integer (optional)
        :param d: The day, as an integer (optional)
        :param iso_string: A string representing the date in the format YYYYMMDD. Month and day are optional.
        """
        if y is not None:
            year = min(max(y, datetime.MINYEAR), datetime.MAXYEAR)
            month = m if (m is not None and 0 < m <= 12) else 1
            day = d if (d is not None and 0 < d <= 31) else 1
        elif iso_string is not None:
            # Replace question marks with first valid field
            iso_string = iso_string.replace("??", "01")

            parsed = parser.isoparse(iso_string)
            return datetime.datetime.__new__(cls, parsed.year, parsed.month, parsed.day)
        else:
            raise TypeError("Must either specify a value for year, or a date string")

        return datetime.datetime.__new__(cls, year, month, day)

    @classmethod
    def today(cls):
        today = datetime.date.today()
        return DateWrapper(today.year, today.month, today.day)

    def __init__(self, y=None, m=None, d=None, iso_string=None):
        if y is not None:
            self.y = min(max(y, datetime.MINYEAR), datetime.MAXYEAR)
            self.m = m if (m is None or 0 < m <= 12) else 1
            self.d = d if (d is None or 0 < d <= 31) else 1
        elif iso_string is not None:
            # Remove any hyphen separators
            iso_string = iso_string.replace("-", "")
            length = len(iso_string)

            if length < 4:
                raise ValueError("Invalid value for year")

            self.y = int(iso_string[:4])
            self.m = None
            self.d = None

            # Month and day are optional. Sometimes fields are missing or contain ??
            if length >= 6:
                try:
                    self.m = int(iso_string[4:6])
                except ValueError:
                    pass
                if length >= 8:
                    try:
                        self.d = int(iso_string[6:8])
                    except ValueError:
                        pass

        else:
            raise TypeError("Must specify a value for year or a date string")

    def __lt__(self, other):
        if self.y != other.y:
            return self.y < other.y
        elif self.m is None:
            return False
        else:
            if other.m is None:
                return True
            elif self.m == other.m:
                if self.d is None:
                    return False
                else:
                    if other.d is None:
                        return True
                    else:
                        return self.d < other.d
            else:
                return self.m < other.m

    def __eq__(self, other):
        if self.y != other.y:
            return False
        elif self.m is not None and other.m is not None:
            if self.d is not None and other.d is not None:
                return self.d == other.d
            else:
                return self.m == other.m
        else:
            return self.m == other.m
