package com.somrik.expenseiq

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.activity.viewModels
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import com.somrik.expenseiq.data.pref.ThemeMode
import com.somrik.expenseiq.presentation.navigation.ExpenseIQNavGraph
import com.somrik.expenseiq.presentation.viewmodel.MainViewModel
import com.somrik.expenseiq.ui.theme.ExpenseIQTheme
import dagger.hilt.android.AndroidEntryPoint

@AndroidEntryPoint
class MainActivity : ComponentActivity() {
    private val viewModel: MainViewModel by viewModels()

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        setContent {
            val themeMode by viewModel.themeMode.collectAsState()
            val darkTheme = when (themeMode) {
                ThemeMode.LIGHT -> false
                ThemeMode.DARK -> true
                ThemeMode.SYSTEM -> androidx.compose.foundation.isSystemInDarkTheme()
            }

            ExpenseIQTheme(darkTheme = darkTheme) {
                ExpenseIQNavGraph()
            }
        }
    }
}
