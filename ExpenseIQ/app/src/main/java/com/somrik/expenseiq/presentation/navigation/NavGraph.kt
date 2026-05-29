package com.somrik.expenseiq.presentation.navigation

import androidx.compose.animation.EnterTransition
import androidx.compose.animation.ExitTransition
import androidx.compose.foundation.layout.padding
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.alpha
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.navigation.NavType
import androidx.navigation.compose.*
import androidx.navigation.navArgument
import com.somrik.expenseiq.presentation.screens.accounts.AccountDetailScreen
import com.somrik.expenseiq.presentation.screens.accounts.AccountsScreen
import com.somrik.expenseiq.presentation.screens.more.CategoryManagerScreen
import com.somrik.expenseiq.presentation.screens.more.GroupManagerScreen
import com.somrik.expenseiq.presentation.screens.more.MoreScreen
import com.somrik.expenseiq.presentation.screens.stats.StatsScreen
import com.somrik.expenseiq.presentation.screens.transactions.AddEditTransactionScreen
import com.somrik.expenseiq.presentation.screens.transactions.TransactionsScreen
import com.somrik.expenseiq.ui.theme.ExpenseRed
import com.somrik.expenseiq.ui.theme.SurfaceWhite
import com.somrik.expenseiq.ui.theme.TextSecondary

sealed class Screen(val route: String, val label: String, val icon: ImageVector) {
    object Transactions : Screen("transactions", "Trans.", Icons.Default.Receipt)
    object Stats : Screen("stats", "Stats", Icons.Default.BarChart)
    object Accounts : Screen("accounts", "Accounts", Icons.Default.AccountBalance)
    object More : Screen("more", "More", Icons.Default.MoreHoriz)
}

@Composable
fun ExpenseIQNavGraph() {
    val navController = rememberNavController()
    val bottomItems = listOf(Screen.Transactions, Screen.Stats, Screen.Accounts, Screen.More)
    val navBackStack by navController.currentBackStackEntryAsState()
    val currentRoute = navBackStack?.destination?.route

    val showBottomBar = currentRoute in bottomItems.map { it.route }

    Scaffold(
        bottomBar = {
            if (showBottomBar) {
                NavigationBar(containerColor = MaterialTheme.colorScheme.surface) {
                    bottomItems.forEach { screen ->
                        NavigationBarItem(
                            selected = currentRoute == screen.route,
                            onClick = {
                                if (currentRoute != screen.route) {
                                    navController.navigate(screen.route) {
                                        popUpTo(navController.graph.startDestinationId) {
                                            saveState = true
                                        }
                                        launchSingleTop = true
                                        restoreState = true
                                    }
                                }
                            },
                            icon = { Icon(screen.icon, screen.label) },
                            label = { Text(screen.label, modifier = Modifier.alpha(0f)) },
                            alwaysShowLabel = true,
                            colors = NavigationBarItemDefaults.colors(
                                selectedIconColor = ExpenseRed,
                                selectedTextColor = ExpenseRed,
                                unselectedIconColor = TextSecondary,
                                unselectedTextColor = TextSecondary,
                                indicatorColor = SurfaceWhite
                            )
                        )
                    }
                }
            }
        }
    ) { innerPadding ->
        NavHost(
            navController = navController,
            startDestination = Screen.Transactions.route,
            modifier = Modifier.padding(innerPadding),
            enterTransition = { EnterTransition.None },
            exitTransition = { ExitTransition.None },
            popEnterTransition = { EnterTransition.None },
            popExitTransition = { ExitTransition.None }
        ) {
            composable(Screen.Transactions.route) {
                TransactionsScreen(
                    onAddTransaction = { navController.navigate("add_transaction") },
                    onEditTransaction = { id -> navController.navigate("edit_transaction/$id") }
                )
            }
            composable(Screen.Stats.route) { StatsScreen() }
            composable(Screen.Accounts.route) {
                AccountsScreen(
                    onAccountClick = { id -> navController.navigate("account_detail/$id") }
                )
            }
            composable(Screen.More.route) {
                MoreScreen(
                    onManageCategories = { navController.navigate("manage_categories") },
                    onManageGroups = { navController.navigate("manage_groups") }
                )
            }
            composable("manage_categories") {
                CategoryManagerScreen(onBack = { navController.popBackStack() })
            }
            composable("manage_groups") {
                GroupManagerScreen(onBack = { navController.popBackStack() })
            }
            composable("add_transaction") {
                AddEditTransactionScreen(onDone = { navController.popBackStack() })
            }
            composable(
                "add_transaction_for/{accountId}",
                arguments = listOf(navArgument("accountId") { type = NavType.LongType })
            ) { backStack ->
                val accountId = backStack.arguments?.getLong("accountId")
                AddEditTransactionScreen(
                    defaultAccountId = accountId,
                    onDone = { navController.popBackStack() }
                )
            }
            composable(
                "edit_transaction/{id}",
                arguments = listOf(navArgument("id") { type = NavType.LongType })
            ) { backStack ->
                val id = backStack.arguments?.getLong("id")
                AddEditTransactionScreen(
                    transactionId = id,
                    onDone = { navController.popBackStack() }
                )
            }
            composable(
                "account_detail/{accountId}",
                arguments = listOf(navArgument("accountId") { type = NavType.LongType })
            ) { backStack ->
                val accountId = backStack.arguments?.getLong("accountId") ?: return@composable
                AccountDetailScreen(
                    accountId = accountId,
                    onBack = { navController.popBackStack() },
                    onAddTransaction = { accId ->
                        navController.navigate("add_transaction_for/$accId")
                    },
                    onEditTransaction = { id -> navController.navigate("edit_transaction/$id") }
                )
            }
        }
    }
}
