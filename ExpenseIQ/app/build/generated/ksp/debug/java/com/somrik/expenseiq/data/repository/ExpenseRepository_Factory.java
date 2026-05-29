package com.somrik.expenseiq.data.repository;

import com.somrik.expenseiq.data.db.dao.AccountDao;
import com.somrik.expenseiq.data.db.dao.AccountGroupDao;
import com.somrik.expenseiq.data.db.dao.CategoryDao;
import com.somrik.expenseiq.data.db.dao.TransactionDao;
import dagger.internal.DaggerGenerated;
import dagger.internal.Factory;
import dagger.internal.QualifierMetadata;
import dagger.internal.ScopeMetadata;
import javax.annotation.processing.Generated;
import javax.inject.Provider;

@ScopeMetadata("javax.inject.Singleton")
@QualifierMetadata
@DaggerGenerated
@Generated(
    value = "dagger.internal.codegen.ComponentProcessor",
    comments = "https://dagger.dev"
)
@SuppressWarnings({
    "unchecked",
    "rawtypes",
    "KotlinInternal",
    "KotlinInternalInJava",
    "cast"
})
public final class ExpenseRepository_Factory implements Factory<ExpenseRepository> {
  private final Provider<AccountGroupDao> accountGroupDaoProvider;

  private final Provider<AccountDao> accountDaoProvider;

  private final Provider<CategoryDao> categoryDaoProvider;

  private final Provider<TransactionDao> transactionDaoProvider;

  public ExpenseRepository_Factory(Provider<AccountGroupDao> accountGroupDaoProvider,
      Provider<AccountDao> accountDaoProvider, Provider<CategoryDao> categoryDaoProvider,
      Provider<TransactionDao> transactionDaoProvider) {
    this.accountGroupDaoProvider = accountGroupDaoProvider;
    this.accountDaoProvider = accountDaoProvider;
    this.categoryDaoProvider = categoryDaoProvider;
    this.transactionDaoProvider = transactionDaoProvider;
  }

  @Override
  public ExpenseRepository get() {
    return newInstance(accountGroupDaoProvider.get(), accountDaoProvider.get(), categoryDaoProvider.get(), transactionDaoProvider.get());
  }

  public static ExpenseRepository_Factory create(Provider<AccountGroupDao> accountGroupDaoProvider,
      Provider<AccountDao> accountDaoProvider, Provider<CategoryDao> categoryDaoProvider,
      Provider<TransactionDao> transactionDaoProvider) {
    return new ExpenseRepository_Factory(accountGroupDaoProvider, accountDaoProvider, categoryDaoProvider, transactionDaoProvider);
  }

  public static ExpenseRepository newInstance(AccountGroupDao accountGroupDao,
      AccountDao accountDao, CategoryDao categoryDao, TransactionDao transactionDao) {
    return new ExpenseRepository(accountGroupDao, accountDao, categoryDao, transactionDao);
  }
}
