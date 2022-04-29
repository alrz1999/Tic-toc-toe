class TicTocToe:
    def __init__(self, user1: str, user2: str):
        self.user1 = user1
        self.user2 = user2
        self.current_user = 1
        self.board = [[0 for _ in range(3)] for _ in range(3)]
        self.winner = 0

    def place_mark(self, user: str, row: int, col: int):
        game_userid = self.get_game_userid(user)

        if self.has_game_finished():
            raise Exception()

        if game_userid != self.current_user:
            raise Exception()
        self.validate_coordinate(row, col)
        self.board[row][col] = self.current_user
        self.change_current_user()
        self._set_winner_if_exists(row, col)

    def get_game_userid(self, user):
        if self.user1 == user:
            return 1
        elif self.user2 == user:
            return 2
        else:
            raise Exception()

    def get_game_opponent_userid(self, user):
        if self.user1 == user:
            return 2
        elif self.user2 == user:
            return 1
        else:
            raise Exception()

    def validate_coordinate(self, row, col):
        if row < 0 or row > 2:
            raise Exception()
        if col < 0 or col > 2:
            raise Exception()
        if self.board[row][col] != 0:
            raise Exception()

    def change_current_user(self):
        if self.current_user == 1:
            self.current_user = 2
        else:
            self.current_user = 1

    def has_game_finished(self):
        if self.winner != 0:
            return True
        for i in range(3):
            for j in range(3):
                if self.board[i][j] == 0:
                    return False
        return True

    def _set_winner_if_exists(self, row, col):
        probable_winner = self.board[row][col]

        if self._check_horizontal(row, col) or self._check_vertical(row, col) or self._check_diagonal(row, col):
            self.winner = probable_winner

    def _check_horizontal(self, row, col):
        cell_value = self.board[row][col]
        counter = 0
        for i in range(-2, 3):
            target_row = row + i
            if 0 <= target_row < 3 and self.board[target_row][col] == cell_value:
                counter += 1
        return counter == 3

    def _check_vertical(self, row, col):
        cell_value = self.board[row][col]
        counter = 0
        for i in range(-2, 3):
            target_col = col + i
            if 0 <= target_col < 3 and self.board[row][target_col] == cell_value:
                counter += 1
        return counter == 3

    def _check_diagonal(self, row, col):
        cell_value = self.board[row][col]
        counter = 0
        for i in range(-2, 3):
            target_row = row + i
            target_col = col + i
            if 0 <= target_col < 3 and 0 <= target_row < 3:
                target_value = self.board[target_row][target_col]
                if target_value == cell_value:
                    counter += 1
        if counter == 3:
            return True

        counter = 0
        for i in range(-2, 3):
            target_row = row - i
            target_col = col + i
            if 0 <= target_col < 3 and 0 <= target_row < 3:
                target_value = self.board[target_row][target_col]
                if target_value == cell_value:
                    counter += 1
        if counter == 3:
            return True
